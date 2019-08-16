import os
import json
import yaml
import gnupg
import emails
import datetime
import tempfile
import namegenerator
import python_terraform
from pathlib import Path
from emails.template import JinjaTemplate as T

from terrascript import Terrascript, backend, terraform, provider
import terrascript.aws.r as aws

# python -m smtpd -n -c DebuggingServer localhost:8002
#  docker run --rm  -p 1025:1025 -p 1080:1080  schickling/mailcatcher
# gpg --export-secret-keys -a C6F2B16E > my_private_key.asc
# gpg --export -a C6F2B16E > my_public_key.asc
# gpg --dearmor the-asc-file.asc covert asc to pgp

ENVIRONMENT = os.getenv('ENVIRONMENT', 'testing')
APPLICATION = os.getenv('APPLICATION', 'wurkflow')
PROFILE = os.getenv('PROFILE', 'VI-NWOT-TESTING')
REGION  = os.getenv('REGION', 'eu-central-1')
TEAM    = os.getenv('TEAM', 'POC')

SMTP_SERVER = os.getenv('SMTP_SERVER', 'localhost')
SMTP_PORT = os.getenv('SMTP_PORT', 1025)
SMTP_SSL = int(os.getenv('SMTP_SSL', 0))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', None)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', None)

REMOTE_STATE_S3_BUCKET = os.getenv('REMOTE_STATE_S3_BUCKET', 'tmde2-testing-terraform-state')
ROOT_PROFILE = os.getenv('ROOT_PROFILE', 'VI-NWOT-TESTING')

ptf = python_terraform.Terraform()
gpg = gnupg.GPG(gnupghome='./gpghome')

s3_backend = backend('s3', bucket=REMOTE_STATE_S3_BUCKET,
                     key=f"path/to/{TEAM}/{ENVIRONMENT}/{APPLICATION}-terraform.tfstate",
                     region=REGION,
                     profile=ROOT_PROFILE)

ts = Terrascript()
ts += terraform(backend=s3_backend)
# Add a provider (+= syntax)
ts += provider('aws', profile=PROFILE, region=REGION)

TF_YAML_MAP = {
    's3': aws.s3_bucket,
    'rds': aws.rds_cluster,
}

MAIL_FROM = ('Infra Provisioner', 'infraprovisioner@mindcurv.com')

SUCCESS_MESSAGE = """
Hi there, your infra has been planned/applied

The output is attached and has been pgp encrypted with the following ids

------
{% for email, key in to %}
{{ email }}: {{ key }}
{% endfor %}
------
"""

ERROR_MESSAGE = """
Sorry, something went wrong provisioning your system
------
{{ stderr }}
------
"""

EMAIL_DATA = dict(
    success=dict(subject='Congrats your infra was provisioned', message=SUCCESS_MESSAGE),
    error=dict(subject='Error your infra could not be provisioned', message=ERROR_MESSAGE),
)

def lookup_keys(emails:list) -> tuple:
    for email in emails:
        try:
            yield email, gpg.search_keys(email, 'pgp.uni-mainz.de')[0]
        except:
            yield email, None


def import_keys(keys:list):
        return gpg.recv_keys('pgp.uni-mainz.de', *keys)


def send_email(to:tuple, message_type:str, attachment:str, mail_from:tuple=('Infra Provisioner', 'ross.crawford@mindcurv.com')):
    filename = f"terraform-{message_type}-output.txt.asc"

    to_emails, recipient_keys = zip(*to)
    encrypted_ascii_data = gpg.encrypt(attachment,
                                       recipient_keys,
                                       always_trust=True)

    assert encrypted_ascii_data.ok is True, f"Invalid GPG Key {encrypted_ascii_data.stderr} recipients {to}"

    subject = EMAIL_DATA.get(message_type).get('subject')
    body = EMAIL_DATA.get(message_type).get('message')

    message = emails.html(text=T(body),
                          subject=T(subject),
                          mail_from=MAIL_FROM)
    
    message.attach(data=bytes(str(encrypted_ascii_data).encode('utf8')),
                   filename=filename)
    message.send(to=to_emails,
                render={
                    'stderr': encrypted_ascii_data.stderr,
                    'to': to
                },
                smtp={'host': SMTP_SERVER, 'port': SMTP_PORT, 'ssl': SMTP_SSL, 'user': SMTP_USERNAME, 'password': SMTP_PASSWORD})

def get_recipients_from_pgp(recipient_emails:list) -> list:
    recipient_key_ids = []

    recipients = [(email, key) for email, key in lookup_keys(emails=recipient_emails)]
    recipients_filtered = [(email, recipient.get('keyid')) for email, recipient in recipients if recipient]
    resp = import_keys(keys=[key for email, key in recipients_filtered])
    return recipients_filtered

def terraform() -> tuple:
    return_code, stdout, stderr = ptf.init()

    return_code, stdout, stderr = ptf.plan(refresh=True, out='plan')
    # return_code, stdout, stderr = ptf.apply()
    response = stdout if not stderr else stderr
    return response, return_code

def random_name(type:str) -> str:
    return f"{type}-{namegenerator.gen()}"


#
# User input YAML
#
provision = yaml.load(Path('provision.yaml').read_bytes(), Loader=yaml.FullLoader)

#
# Extract the notify component
#
notify = provision.pop('notify')
if notify:
    # tuple of email, key
    recipients = get_recipients_from_pgp(recipient_emails=[i for i in notify.get('email', [])])

#
# Parse the yaml
#
for provider in provision:
    #print(f"----- output for provider: {provider.upper()} -----")
    for resource, data in provision.get(provider).items():
        #print(f"----- output for resource: {resource} -----")
        for item in data.get('items', []):
            api = TF_YAML_MAP.get(resource)
            item_name = item.pop('name', random_name(type=resource))
            ts.add(
                api(item_name, **item)
            )

data = ts.dump()
Path('main.tf.json').write_text(data)

tf_response, tf_code = terraform()

# with open('tf_response.log', 'w') as f:
#     f.write(tf_response)

# with tempfile.TemporaryFile(mode='w+b') as file:
#     file.write(bytes(tf_response.encode('ascii')))
#     file.seek(0)
send_email(to=recipients,
           attachment=tf_response,
           message_type='success' if tf_code != 1 else 'error')

# print(data)