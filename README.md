# TerraYaml - Ship of the seas

A simple CRD to handle terraform operations for developers via a simple yaml file
that maps 1 to 1 to the terraform resource documentation

```sh
cd terrayaml
# Start the server in dev mode (will deploy using docker container)
kopf run terrayaml/handler.py --verbose --dev

# setup the CRD
kc apply -f k8s/crd-terrayaml.yaml

# install a basic example
kc apply -f k8s/example-terrayaml.yaml
# delete it if you need to
kc delete -f k8s/example-terrayaml.yaml

# patch the planId (this will happen internally but you can override)
kc patch ty my-ty-example --type merge -p '{"spec": {"planId":"./runs/tmpamkb_idq"}}'

# set apply to true to make it happen
kc patch ty my-ty-example --type merge -p '{"spec": {"apply": true}}'
```