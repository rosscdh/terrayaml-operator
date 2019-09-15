import os
import json
import yaml
import gnupg
import random
import string
import emails
import jinja2
import datetime
import tempfile
import namegenerator
import python_terraform
from pathlib import Path
from emails.template import JinjaTemplate as T
from kopf.engines.logging import ObjectLogger as KopfObjectLogger

from terrascript import Terrascript, Terraform, Provider
import terrascript.aws.r as aws


PROFILE = os.getenv('PROFILE', 'RBMH-MIT-NONPROD')
REGION  = os.getenv('REGION', 'eu-west-1')

SMTP_SERVER = os.getenv('SMTP_SERVER', 'localhost')
SMTP_PORT = os.getenv('SMTP_PORT', 1025)
SMTP_SSL = int(os.getenv('SMTP_SSL', 0))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', None)
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', None)

REMOTE_STATE_S3_BUCKET = os.getenv('REMOTE_STATE_S3_BUCKET', 'rbmh-mit-cc2meadow-shared-tf-remote-state')
ROOT_PROFILE = os.getenv('ROOT_PROFILE', 'RBMH-MIT-NONPROD')

gpg = gnupg.GPG(gnupghome='/Users/ross/Desktop/provisioner/camel/gnupghome')


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

def random_password(value=None, length:int=15) -> str:
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def random_name(value:str='') -> str:
    if value:
        return f"{value}-{namegenerator.gen()}"
    else:
        return f"{namegenerator.gen()}"


def lookup_keys(emails:list) -> tuple:
    for email in emails:
        try:
            yield email, gpg.search_keys(email, 'pgp.uni-mainz.de')[0]
        except:
            yield email, None


def import_keys(keys:list):
        return gpg.recv_keys('pgp.uni-mainz.de', *keys)


def send_email(to:tuple,
               message_type:str,
               attachment:str,
               mail_from:tuple=('Infra Provisioner', 'ross.crawford@mindcurv.com')):
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

def terraform(working_dir:str, data:str, logger:KopfObjectLogger, apply:bool=False, planId:str='') -> tuple:
    logger.info(f"WORKING IN DIR: {working_dir}")
    Path(f"{working_dir}/main.tf.json").write_text(data)

    ptf = python_terraform.Terraform(working_dir=working_dir)
    return_code, stdout, stderr = ptf.init()
    assert return_code != 1, f"Terraform Init Failed {stderr}"
    logger.info('TERRAFORM INIT COMPLETE')

    return_code, stdout, stderr = ptf.plan(refresh=True, out='plan')
    # import pdb;pdb.set_trace()
    # return_code, stdout, stderr = ptf.apply()
    # logger.info('TERRAFORM APPLY COMPLETE')
    response = stdout if not stderr else stderr
    logger.info(f"TERRAFORM PLAN COMPLETE {response}")
    return response, return_code

def terraform_apply(planId:str, logger:KopfObjectLogger) -> tuple:
    logger.info(f"PLANID: {planId}")
    #@TODO check if planId exists throw kopf eception if not
    ptf = python_terraform.Terraform(working_dir=planId)
    # return_code, stdout, stderr = ptf.apply(refresh=True, auto_apply=True)
    return_code, stdout, stderr = 0, 'all good', ''
    response = stdout if not stderr else stderr
    logger.info(f"TERRAFORM APPLY COMPLETE: {return_code} {response}")
    return response, return_code

def process(terrayaml:str, metadata:dict,
            logger:KopfObjectLogger) -> str:
    #
    # User input YAML
    #
    env = jinja2.Environment()
    env.filters['random_password'] = random_password
    env.filters['random_name'] = random_name

    template = T(template_text=terrayaml, environment=env).render(**metadata)

    provision = yaml.load(template, Loader=yaml.FullLoader)
    logger.info(f"provision this template {provision}")
    # print(provision)

    #
    # Start terraform
    #
    meta                = provision.pop('meta', {})
    team                = meta.get('team', 'oss')
    environment         = meta.get('environment', 'testing')
    application         = meta.get('application', 'wurkflow')
    statefile_region    = meta.get('statefile_region', 'eu-west-1')

    ts = Terrascript()
    ts += Terraform(
        required_version=">= 0.12.7"
    ).backend(
        "s3",
        bucket=REMOTE_STATE_S3_BUCKET,
        key=f"k8/camel-operator/{team}/{environment}/{application}-terraform.tfstate",
        region=statefile_region,
        profile=ROOT_PROFILE
    )

    #
    # Extract the notify component
    #
    notify = provision.pop('notify')
    if notify:
        # tuple of email, key
        recipient_emails = notify.get('email', [])
        # append out infra provisioner email
        recipient_emails.append('infraprovisioner@mindcurv.com')
        recipients = get_recipients_from_pgp(recipient_emails=recipient_emails)
        logger.info(f"notify these emails: {recipient_emails}")

    #
    # Parse the yaml
    #
    for provider in provision:
        #print(f"----- output for provider: {provider.upper()} -----")
        for resource, data in provision.get(provider).items():
            #print(f"----- output for resource: {resource} -----")
            for item in data.get('items', []):
                api = TF_YAML_MAP.get(resource)
                item_name = item.pop('name', random_name(value=resource))
                ts.add(
                    api(item_name, **item)
                )

    # Add a provider (+= syntax)
    ts += Provider('aws',
                skip_metadata_api_check=True,
                profile=PROFILE,
                region=REGION)
    data = ts.dump()

    # Plan
    working_dir = tempfile.mkdtemp(dir='./runs')
    tf_response, tf_code = terraform(working_dir=working_dir,
                                    data=data,
                                    logger=logger)
    logger.info(f"Terraform Plan result: {tf_response}")

    if recipients:
        logger.info(f"Send email to {recipients}")
        send_email(to=recipients,
                attachment=tf_response,
                message_type='success' if tf_code != 1 else 'error')
    else:
        logger.info('No recipients defined')
    logger.info(f"PlanId is {working_dir}")
    return f"{working_dir}"

def process_apply(planId:str,
                  metadata:dict,
                  logger:KopfObjectLogger) -> str:
    tf_response, tf_code = terraform_apply(planId=planId,
                                           logger=logger)
    logger.info(f"Terraform Apply result: {tf_response}")