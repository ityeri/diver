#!/usr/bin/env python3
"""
This is reproducable script. Fixed by version
"""
import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "v1.6.1"
KINDS: tuple[str, ...] = (
    "gatewayclasses",
    "gateways",
    "httproutes",
    "grpcroutes",
    "referencegrants",
    "tlsroutes",
    "backendtlspolicies",
    "tcproutes",
    "udproutes",
)
CHANNELS: tuple[str, ...] = ("standard", "experimental")
URL = (
    "https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/"
    "{version}/config/crd/{channel}/gateway.networking.k8s.io_{kind}.yaml"
)
TIMEOUT = 60


def _get(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "diver-fetch-gateway-crds"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _normalize(text: str) -> str:
    text = text.strip()
    if text.startswith("---"):
        text = text[3:].lstrip()
    return text + "\n"


def fetch_crd(version: str, kind: str, verbose: bool) -> tuple[str, str]:
    for channel in CHANNELS:
        url = URL.format(version=version, channel=channel, kind=kind)
        text = _get(url)
        if text is None:
            continue
        if "kind: CustomResourceDefinition" not in text:
            raise SystemExit(f"unexpected payload (404 page?): {url}")
        if verbose:
            print(f"  {kind:22} {channel:13} {len(text):>8} bytes", file=sys.stderr)
        return _normalize(text), channel
    raise SystemExit(f"CRD not found: {kind} (tried {CHANNELS}) in gateway-api {version}")


def build(version: str, verbose: bool) -> str:
    docs = [fetch_crd(version, kind, verbose) for kind in KINDS]
    return "".join(f"---\n{doc}" for doc, _ in docs)


def main(argv: list[str] | None = None) -> int:
    default_out = Path(__file__).resolve().parent / "raw-manifests.yaml"
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default=VERSION, help=f"gateway-api tag (default {VERSION})")
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--check", action="store_true", help="차이만 검사 (다르면 exit 1)")
    ap.add_argument("-v", "--verbose", action="store_true", help="항목별 출력")
    args = ap.parse_args(argv)

    content = build(args.version, args.verbose)
    digest = hashlib.sha256(content.encode()).hexdigest()
    docs = content.count("\n---\n") + 1
    old = args.out.read_text() if args.out.exists() else None

    if args.check:
        if old is None:
            print(f"MISSING {args.out}", file=sys.stderr)
            return 1
        if old != content:
            print(f"DIFF {args.out} (gateway-api {args.version})", file=sys.stderr)
            return 1
        print(f"OK {args.out} ({docs} CRDs, {len(content)} bytes, sha256 {digest[:12]})")
        return 0

    if old == content:
        print(f"unchanged {args.out} ({docs} CRDs, sha256 {digest[:12]})")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(content)
    print(f"wrote {args.out} ({docs} CRDs, {len(content)} bytes, sha256 {digest[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

