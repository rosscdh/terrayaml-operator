kopf run camel/handler.py --verbose --dev
kc apply -f k8s/crd-terrayaml.yaml
kc apply -f k8s/example-terrayaml.yaml
kc delete -f k8s/example-terrayaml.yaml
kc patch ty my-ty-example --type merge -p '{"spec": {"planId":"./runs/tmpamkb_idq"}}'
kc patch ty my-ty-example --type merge -p '{"spec": {"apply": true}}'