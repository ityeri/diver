#!/usr/bin/env bash
# Flux 매니페스트 로컬 검증 (클러스터 불필요).
# usage: validate-flux.sh [-v] [repo-root]     -v: 정상 항목까지 전부 출력
# 기본 동작: 문제(invalid/error/render fail)만 출력하고, 정상 항목은 스테이지별 요약 1줄로 끝낸다.
# env override: KC/KZ/FLUX(바이너리 경로), KC_CACHE(스키마 캐시 디렉터리)
set -u
V=0
while [ $# -gt 0 ]; do case "$1" in -v|--verbose) V=1; shift;; *) break;; esac; done
if [ $# -ge 1 ]; then REPO=$1
else REPO=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "git 저장소가 아님 — repo 루트를 인자로" >&2; exit 2; }
fi
cd "$REPO" || exit 2
KC=${KC:-kubeconform}; KZ=${KZ:-kustomize}; FLUX=${FLUX:-flux}
CRD='https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
CACHE=${KC_CACHE:-$HOME/.cache/kubeconform}; mkdir -p "$CACHE"
OPTS="-strict -verbose -summary -ignore-missing-schemas -cache $CACHE -schema-location default -schema-location $CRD"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
rc=0; probs=0
banner() { printf '\n================\n%s\n================\n\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }
fn_prob() { grep -vE ' is valid$| skipped$|^Summary:' "$1" || true; }
fn_sum() { sed -n 's/.*Valid: \([0-9]*\), Invalid: \([0-9]*\), Errors: \([0-9]*\), Skipped: \([0-9]*\).*/\1 \2 \3 \4/p' "$1"; }
fn_agg() { awk '{v+=$1;i+=$2;e+=$3;s+=$4} END{printf "%d %d %d %d", v+0,i+0,e+0,s+0}' "$1"; }
print_stage() {
  local d="$1" lab="$2" el="$3" n c
  n=$(awk "{s+=\$1} END{print s+0}" "$d/cnt")
  c=$(grep -c . "$d/prob" || true)
  if [ "$c" -gt 0 ]; then rc=1; probs=$((probs+c)); [ "$V" -eq 0 ] && cat "$d/prob"; fi
  set -- $(fn_agg "$d/sum")
  printf -- '-- %s: %s items -> Valid %s, Invalid %s, Errors %s, Skipped %s (%ss)\n' "$lab" "$n" "$1" "$2" "$3" "$4" "$el"
}

banner 'kubeconform stage (raw files)'
if ! have "$KC"; then echo "SKIP: $KC 없음"; else
  L="$T/files"; : > "$T/cnt"; : > "$T/prob"; : > "$T/sum"
  find . -path ./.git -prune -o -name '*.yaml' -print | sort | while IFS= read -r f; do
grep -qE '^[[:space:]]*kind:' "$f" && printf '%s\0' "$f"
  done > "$L"
  if [ ! -s "$L" ]; then echo "검증할 매니페스트 없음"; else
    t0=$SECONDS
    tr -cd '\0' < "$L" | wc -c >> "$T/cnt"
    xargs -0 "$KC" $OPTS < "$L" > "$T/o" 2>&1 || true
    [ "$V" -eq 1 ] && cat "$T/o"
    fn_prob "$T/o" > "$T/prob"; fn_sum "$T/o" > "$T/sum"
    print_stage "$T" 'raw yaml' "$((SECONDS-t0))"
  fi
fi

banner 'kustomize stage (렌더 결과)'
if ! have "$KZ" || ! have "$KC"; then echo "SKIP: kustomize/kubeconform 없음"; else
  t0=$SECONDS; : > "$T/prob"; : > "$T/sum"; : > "$T/cnt"
  find . -path ./.git -prune -o -name kustomization.yaml -print | sed 's|/kustomization.yaml$||' | sort \
  | while IFS= read -r d; do
    echo 1 >> "$T/cnt"
    if ! "$KZ" build "$d" > "$T/r.yaml" 2> "$T/e"; then
      printf 'RENDER FAIL %s\n' "$d" >> "$T/prob"; sed -n '1,3p' "$T/e" | cut -c1-300 >> "$T/prob"
      printf '0 0 1 0\n' >> "$T/sum"; continue
    fi
    "$KC" $OPTS "$T/r.yaml" > "$T/o" 2>&1 || true
    [ "$V" -eq 1 ] && { printf '\n-- kustomize build %s\n' "$d"; cat "$T/o"; }
    fn_prob "$T/o" | sed "s|^|$d: |" >> "$T/prob"
    fn_sum "$T/o" >> "$T/sum"
  done
  print_stage "$T" 'kustomize' "$((SECONDS-t0))"
fi

banner 'flux build stage (컨트롤러와 동일 렌더)'
if ! have "$FLUX" || ! have "$KC"; then echo "SKIP: flux/kubeconform 없음"; else
  t0=$SECONDS; : > "$T/prob"; : > "$T/sum"; : > "$T/cnt"
  find ./clusters -name '*.yaml' -not -path '*/flux-system/*' | sort | while IFS= read -r k; do
    echo 1 >> "$T/cnt"
    n=$(awk '/^metadata:/{m=1} m&&/^  name:/{sub(/^  name: */,"");print;exit}' "$k")
    p=$(sed -n 's/^  path: *//p' "$k" | head -1)
    if ! "$FLUX" build ks "$n" --path "$p" --kustomization-file "$k" --dry-run > "$T/r.yaml" 2> "$T/e"; then
      printf 'RENDER FAIL %s (path=%s)\n' "$n" "$p" >> "$T/prob"; sed -n '1,3p' "$T/e" | cut -c1-300 >> "$T/prob"
      printf '0 0 1 0\n' >> "$T/sum"; continue
    fi
    "$KC" $OPTS "$T/r.yaml" > "$T/o" 2>&1 || true
[ "$V" -eq 1 ] && { printf '\n-- flux build %s\n' "$n"; cat "$T/o"; }
    fn_prob "$T/o" | sed "s|^|$n: |" >> "$T/prob"
    fn_sum "$T/o" >> "$T/sum"
  done
  print_stage "$T" 'flux build' "$((SECONDS-t0))"
fi

printf '\n================\n'
if [ "$rc" -eq 0 ]; then echo 'ALL PASS'; else printf 'FAILED (%s problem lines)\n' "$probs"; fi
exit "$rc"
