#!/usr/bin/env python3
"""Semantic consistency checks for the rendered manifests.

Only covers what kubeconform (JSON schema) cannot:
  1. core/v1 port protocol enums (Service and container ports: TCP, UDP, SCTP)
  2. Gateway API route <-> listener consistency
     - the Gateway and listener referenced by parentRef exist
     - route kind is compatible with the listener protocol (HTTPRoute->HTTP/HTTPS, TCPRoute->TCP, ...)
     - the route namespace is allowed by the listener allowedRoutes (spec default is Same)
     - the backendRef Service and its port exist
  3. Secret reference resolution (env/envFrom/volume -> key exists in Secret|SealedSecret)

usage: validate_semantics.py <rendered.yaml> [...]
output: one line per problem, last line SUMMARY: <docs> <errors> <warnings>
exit code: 1 when errors > 0
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (nix-shell -p python3Packages.pyyaml)", file=sys.stderr)
    sys.exit(2)

PORT_PROTOCOLS = {"TCP", "UDP", "SCTP"}
ROUTE_PROTOCOLS = {
    "HTTPRoute": {"HTTP", "HTTPS"},
    "GRPCRoute": {"HTTP", "HTTPS"},
    "TLSRoute": {"TLS"},
    "TCPRoute": {"TCP"},
    "UDPRoute": {"UDP"},
}
ROUTE_KINDS = set(ROUTE_PROTOCOLS)
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}
problems = []


def err(src, msg):
    problems.append("ERROR %s: %s" % (src, msg))


def load(path):
    src = Path(path).name
    docs = []
    for d in yaml.safe_load_all(Path(path).read_text()):
        if isinstance(d, dict) and d.get("kind"):
            d["__src"] = src
            docs.append(d)
    return docs


def key(d):
    m = d.get("metadata", {})
    return (d.get("kind"), m.get("namespace"), m.get("name"))


def pod_specs(d):
    spec = d.get("spec", {})
    if d.get("kind") in WORKLOAD_KINDS:
        if d.get("kind") == "CronJob":
            spec = spec.get("jobTemplate", {}).get("spec", {})
        yield spec.get("template", {}).get("spec", {}) or {}


def check_ports(d):
    src, kind, name = d["__src"], d.get("kind"), d.get("metadata", {}).get("name")
    if kind == "Service":
        for p in d.get("spec", {}).get("ports", []) or []:
            proto = p.get("protocol", "TCP")
            if proto not in PORT_PROTOCOLS:
                err(src, "Service %s/%s ports[%s].protocol=%r is not one of %s (use appProtocol for HTTP semantics)" % (
                    d.get("metadata", {}).get("namespace"), name, p.get("name", p.get("port")), proto, sorted(PORT_PROTOCOLS)))
    for ps in pod_specs(d):
        for c in (ps.get("containers", []) or []) + (ps.get("initContainers", []) or []):
            for p in c.get("ports", []) or []:
                proto = p.get("protocol", "TCP")
                if proto not in PORT_PROTOCOLS:
                    err(src, "%s %s container %s: containerPort %s protocol=%r is not one of %s" % (
                        kind, name, c.get("name"), p.get("containerPort"), proto, sorted(PORT_PROTOCOLS)))
                if "appProtocol" in p:
                    err(src, "%s %s container %s: containerPort has no appProtocol field" % (kind, name, c.get("name")))


def check_routes(docs, index):
    for d in docs:
        kind = d.get("kind")
        if kind not in ROUTE_KINDS:
            continue
        src = d["__src"]
        m = d.get("metadata", {})
        ns, name = m.get("namespace"), m.get("name")
        for parent in d.get("spec", {}).get("parentRefs", []) or []:
            if parent.get("kind", "Gateway") != "Gateway":
                continue
            gns = parent.get("namespace", ns)
            gw = index.get(("Gateway", gns, parent.get("name")))
            listeners = []
            if gw is None:
                err(src, "%s %s/%s: parentRef Gateway %s/%s not found" % (kind, ns, name, gns, parent.get("name")))
            else:
                listeners = gw.get("spec", {}).get("listeners", []) or []
                section = parent.get("sectionName")
                if section is not None:
                    named = [ls for ls in listeners if ls.get("name") == section]
                    if not named:
                        err(src, "%s %s/%s: sectionName %r no listener named %r on Gateway %s/%s" % (kind, ns, name, section, gns, parent.get("name")))
                    listeners = named
            allowed = ROUTE_PROTOCOLS[kind]
            matching = []
            proto_matched = 0
            for ls in listeners:
                if ls.get("protocol") not in allowed:
                    continue
                proto_matched += 1
                from_ = ((ls.get("allowedRoutes") or {}).get("namespaces") or {}).get("from", "Same")
                if from_ == "Same" and ns != gns:
                    err(src, "%s %s/%s: listener %s defaults to allowedRoutes Same, so a route in namespace %s cannot attach" % (
                        kind, ns, name, ls.get("name"), ns))
                    continue
                matching.append(ls)
            if listeners and not proto_matched:
                err(src, "%s %s/%s: no matching listener (route requires %s, listener protocols %s)" % (
                    kind, ns, name, sorted(allowed), [ls.get("protocol") for ls in listeners]))
            for rule in d.get("spec", {}).get("rules", []) or []:
                for be in rule.get("backendRefs", []) or []:
                    if be.get("kind", "Service") != "Service":
                        continue
                    bns = be.get("namespace", ns)
                    svc = index.get(("Service", bns, be.get("name")))
                    if svc is None:
                        err(src, "%s %s/%s: backendRef Service %s/%s not found" % (kind, ns, name, bns, be.get("name")))
                        continue
                    ports = set()
                    for p in svc.get("spec", {}).get("ports", []) or []:
                        ports.add(p.get("port"))
                        ports.add(p.get("name"))
                    if be.get("port") is not None and be["port"] not in ports:
                        err(src, "%s %s/%s: backendRef %s port=%s not found on the Service (Service ports=%s)" % (
                            kind, ns, name, be.get("name"), be.get("port"), sorted((x for x in ports if x is not None), key=str)))


def secret_keys(index):
    out = {}
    for (kind, ns, name), d in index.items():
        if kind not in ("Secret", "SealedSecret"):
            continue
        keys = set(d.get("data") or {})
        keys |= set(d.get("stringData") or {})
        spec = d.get("spec", {})
        keys |= set(spec.get("encryptedData") or {})
        keys |= set((spec.get("template", {}) or {}).get("data") or {})
        out[(ns, name)] = keys
    return out


def check_secrets(docs, secrets):
    for d in docs:
        if d.get("kind") not in WORKLOAD_KINDS:
            continue
        src, kind = d["__src"], d["kind"]
        m = d.get("metadata", {})
        ns, name = m.get("namespace"), m.get("name")
        for ps in pod_specs(d):
            for c in (ps.get("containers", []) or []) + (ps.get("initContainers", []) or []):
                for e in c.get("env", []) or []:
                    ref = (e.get("valueFrom") or {}).get("secretKeyRef")
                    if not ref:
                        continue
                    have = secrets.get((ns, ref.get("name")))
                    if have is None:
                        err(src, "%s %s/%s %s: env %s -> Secret %s not found" % (kind, ns, name, c.get("name"), e.get("name"), ref.get("name")))
                    elif ref.get("key") not in have:
                        err(src, "%s %s/%s %s: env %s -> key %r not found (present: %s)" % (
                            kind, ns, name, c.get("name"), e.get("name"), ref.get("key"), sorted(have)))
                for ef in c.get("envFrom", []) or []:
                    r = ef.get("secretRef")
                    if r and (ns, r.get("name")) not in secrets:
                        err(src, "%s %s/%s %s: envFrom -> Secret %s not found" % (kind, ns, name, c.get("name"), r.get("name")))
            for v in ps.get("volumes", []) or []:
                s = v.get("secret")
                if not s:
                    continue
                have = secrets.get((ns, s.get("secretName")))
                if have is None:
                    err(src, "%s %s/%s: volume %s -> Secret %s not found" % (kind, ns, name, v.get("name"), s.get("secretName")))
                for item in s.get("items", []) or []:
                    if have and item.get("key") not in have:
                        err(src, "%s %s/%s: volume %s item key %r not found (present: %s)" % (
                            kind, ns, name, v.get("name"), item.get("key"), sorted(have)))


def main(argv):
    if not argv:
        print("usage: validate_semantics.py <rendered.yaml> [...]", file=sys.stderr)
        return 2
    docs = [d for p in argv for d in load(p)]
    index = {key(d): d for d in docs}
    secrets = secret_keys(index)
    for d in docs:
        check_ports(d)
    check_routes(docs, index)
    check_secrets(docs, secrets)
    for p in problems:
        print(p)
    print("SUMMARY: %d %d 0" % (len(docs), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
