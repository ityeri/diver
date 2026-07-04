rm ./infra-ctrls/cilium/raw-manifests.yaml

helm template cilium cilium/cilium \
  --namespace kube-system \
  --include-crds \
  --set ipam.mode=kubernetes \
  --set kubeProxyReplacement=true \
  --set operator.replicas=1 \
  --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
  --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
  --set cgroup.autoMount.enabled=false \
  --set cgroup.hostRoot=/sys/fs/cgroup \
  --set k8sServiceHost=localhost \
  --set k8sServicePort=7445 \
  > ./infra-ctrls/cilium/raw-manifests.yaml
