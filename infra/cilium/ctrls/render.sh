#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

rm -f "$SCRIPT_DIR/raw-manifests.yaml"

helm repo add cilium https://helm.cilium.io/
helm repo update cilium

helm template cilium cilium/cilium \
  --version 1.20.2 \
  --namespace kube-system \
  --include-crds \
  -f "$SCRIPT_DIR/values.yaml" \
  > "$SCRIPT_DIR/raw-manifests.yaml"
