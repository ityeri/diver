#!/usr/bin/env bash
set -euo pipefail

CHART_URL="https://github.com/ultraworkers/hermes-agent-helm-chart/archive/refs/heads/main.tar.gz"
CHART_DIR="/tmp/hermes-agent-helm-chart-main"

rm -f ./modules/hermes-agent/raw-manifests.yaml
rm -rf "$CHART_DIR"

curl -fsSL "$CHART_URL" | tar xz -C /tmp

helm template hermes-agent "$CHART_DIR" \
  --namespace hermes-agent \
  --include-crds \
  -f ./modules/hermes-agent/values.yaml \
  > ./modules/hermes-agent/raw-manifests.yaml

rm -rf "$CHART_DIR"
