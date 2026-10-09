rm ./infra-ctrls/sealed-secrets/raw-manifests.yaml

helm repo add sealed-secrets https://bitnami.github.io/sealed-secrets
helm repo update sealed-secrets

helm template sealed-secrets sealed-secrets/sealed-secrets \
  --namespace sealed-secrets \
  --include-crds \
  -f ./infra-ctrls/sealed-secrets/values.yaml \
  > ./infra-ctrls/sealed-secrets/raw-manifests.yaml

