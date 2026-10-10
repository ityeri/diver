#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

rm -f "$SCRIPT_DIR/raw-manifests.yaml"

helm repo add sealed-secrets https://bitnami.github.io/sealed-secrets
helm repo update sealed-secrets

helm template sealed-secrets sealed-secrets/sealed-secrets \
  --namespace sealed-secrets \
  --include-crds \
  -f "$SCRIPT_DIR/values.yaml" \
  > "$SCRIPT_DIR/raw-manifests.yaml"
