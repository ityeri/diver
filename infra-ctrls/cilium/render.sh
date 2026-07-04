rm ./infra-ctrls/cilium/raw-manifests.yaml

helm repo add cilium https://helm.cilium.io/
helm repo update cilium

helm template cilium cilium/cilium \
  --namespace kube-system \
  --include-crds \
  -f ./infra-ctrls/cilium/values.yaml \
  > ./infra-ctrls/cilium/raw-manifests.yaml

