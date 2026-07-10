rm ./infra-base/cilium/raw-manifests.yaml

helm repo add cilium https://helm.cilium.io/
helm repo update cilium

helm template cilium cilium/cilium \
  --namespace kube-system \
  --include-crds \
  -f ./infra-base/cilium/values.yaml \
  > ./infra-base/cilium/raw-manifests.yaml

