#!/usr/bin/env python3
"""Validate a rendered chargo manifest — catches what `helm lint` cannot see.

Reads `helm template` output — one or more file arguments, or stdin — and enforces the invariants that
matter for a chart whose entire output is ArgoCD objects. Every input is pooled, so a glob over an
`--output-dir` tree is checked as one render: the by-name invariants below need the AppProjects and the
Applications in the same pass to mean anything.

1. NO GLUED DOCUMENT SEPARATOR — a `---` must start its own line. Whitespace trimming (`-}}`) can glue it
   to the previous line, which silently STOPS it from separating documents: two objects then land in the
   SAME YAML document and the later one OVERWRITES the earlier. `grep` cannot see this; a parser can.
   It has shipped before, in a sibling chart, where one Ingress swallowed another.

2. OBJECT COUNT MATCHES — the number of top-level `kind:` lines must equal the number of objects a YAML
   parser actually yields. A mismatch is the generic signature of invariant #1.

3. NO DUPLICATE OBJECT — two objects sharing kind + namespace + name means one values entry silently
   overwrites another's ArgoCD object. The usual cause is two entries resolving to the same name because
   one forgot its own `name:`.

4. EVERY PROJECT IS DECLARED — an Application or ApplicationSet referencing a project no AppProject
   defines is accepted by the API server and then refused by ArgoCD at sync time, which is a slow way to
   find a typo.

5. EVERY DESTINATION IS ALLOWED — the namespace an object deploys into must match a destination of its
   project. Same failure mode: silent until the first sync.

6. NO LEFTOVER TEMPLATE MARKER — a `{{` is legitimate only where ANOTHER engine evaluates it: an
   ApplicationSet's `spec.template` (ArgoCD goTemplate, per leaf) and an ExternalSecret's
   `spec.target.template` (external-secrets, per refresh). Anywhere else it is an unrendered Helm action.

7. ONE NAMESPACE ONLY — every object lands in the same namespace, the ArgoCD one. chargo declares what
   ArgoCD should deploy; it never deploys into an application namespace itself. A secret a workload needs
   belongs beside that workload — created by its chart, or committed as an ExternalSecret next to its
   manifests. Relax this only if chargo ever gains a legitimately cluster-scoped object.

Exit code 1 on violation, with the offending objects named, so CI fails loudly.
"""

import fnmatch
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required (apk add py3-yaml / pip install pyyaml)")

KIND_LINE = re.compile(r"^kind:\s*(\S+)", re.MULTILINE)
# A `---` GLUED to the end of a line: three dashes preceded by a character that is neither a dash nor
# whitespace, which is exactly what "something was printed right before the separator" looks like.
#
# Both exclusions carry their weight. Whitespace lets a legitimately indented `---` through — inside a
# block scalar it is text, not a separator. The dash lets PEM through: `-----BEGIN CERTIFICATE-----`
# ends in three dashes too, and every config block mounting a CA carries two such lines, which is
# enough false positives to make the whole check ignored.
GLUED_SEPARATOR = re.compile(r"[^-\s]---\s*$")
APP_KINDS = {"Application", "ApplicationSet"}


def object_id(obj):
    meta = obj.get("metadata") or {}
    return f"{obj.get('kind')}/{meta.get('namespace', '-')}/{meta.get('name')}"


def find_markers(node, path=""):
    """Yield paths of string leaves still containing `{{`."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from find_markers(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from find_markers(v, f"{path}[{i}]")
    elif isinstance(node, str) and "{{" in node:
        yield path


def read_sources(paths):
    """`(label, text)` per input — every path given, or stdin when none is.

    Several files stay SEPARATE rather than being concatenated: the glued-separator check reports a line
    number, and pooling the texts would report it against the wrong file. Concatenating would also invent
    a document boundary between two renders, or lose one — the very accident this script exists to catch.
    """
    if not paths:
        return [("<stdin>", sys.stdin.read())]
    return [(p, open(p).read()) for p in paths]


def main() -> int:
    sources = read_sources(sys.argv[1:])
    errors = []

    # --- 1. glued `---` -----------------------------------------------------------------------------
    glued = [
        (label, n, line)
        for label, raw in sources
        for n, line in enumerate(raw.splitlines(), start=1)
        if GLUED_SEPARATOR.search(line)
    ]
    if glued:
        errors.append(
            "glued document separator(s) — `---` is not at the start of its line, so it does NOT "
            "separate documents (drop the `-` from the `-}}` that precedes it):"
        )
        errors += [f"    {label} line {n}: {line!r}" for label, n, line in glued]

    # --- 2. declared kinds vs parsed objects --------------------------------------------------------
    declared, objects = [], []
    for label, raw in sources:
        declared += KIND_LINE.findall(raw)
        try:
            objects += [d for d in yaml.safe_load_all(raw) if d]
        except yaml.YAMLError as exc:
            print(f"::error:: {label} is not valid YAML: {exc}", file=sys.stderr)
            return 1

    if len(declared) != len(objects):
        errors.append(
            f"object count mismatch: {len(declared)} `kind:` lines but {len(objects)} parsed objects "
            "→ documents were merged or dropped (an object is silently overwritten)."
        )
        errors.append(f"    declared kinds: {sorted(declared)}")
        errors.append(f"    parsed objects: {sorted(object_id(o) for o in objects)}")

    # --- 3. duplicate objects -----------------------------------------------------------------------
    seen = {}
    for obj in objects:
        key = object_id(obj)
        seen[key] = seen.get(key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            errors.append(
                f"{key} rendered {count} times — two values entries resolve to the same object, so one "
                "overwrites the other (give one of them an explicit `name:`)."
            )

    # --- 4 & 5. projects and destinations -----------------------------------------------------------
    projects = {
        obj["metadata"]["name"]: (obj.get("spec") or {}).get("destinations") or []
        for obj in objects
        if obj.get("kind") == "AppProject"
    }
    for obj in objects:
        if obj.get("kind") not in APP_KINDS:
            continue
        spec = (obj.get("spec") or {}).get("template", {}).get("spec") or obj.get("spec") or {}
        project = spec.get("project")
        if project not in projects:
            errors.append(
                f"{object_id(obj)} targets project {project!r}, which no AppProject in this render "
                "declares — ArgoCD would refuse every sync."
            )
            continue
        namespace = ((spec.get("destination") or {}).get("namespace") or "").strip()
        # A namespace read from the leaf at sync time cannot be checked here.
        if not namespace or "{{" in namespace:
            continue
        allowed = [d.get("namespace", "") for d in projects[project]]
        if not any(fnmatch.fnmatch(namespace, pattern) for pattern in allowed):
            errors.append(
                f"{object_id(obj)} deploys into namespace {namespace!r}, which project {project!r} does "
                f"not allow (destinations: {allowed})."
            )

    # --- 6. leftover template markers ---------------------------------------------------------------
    # Subtrees another engine evaluates, so a `{{` there is intended, not a Helm leftover.
    FOREIGN_TEMPLATES = {
        "ApplicationSet": ("spec", "template"),
        "ExternalSecret": ("spec", "target", "template"),
        "ClusterExternalSecret": ("spec", "externalSecretSpec", "target", "template"),
    }

    def prune(node, path):
        """Copy `node` with the branch at `path` removed."""
        if not path or not isinstance(node, dict) or path[0] not in node:
            return node
        head, rest = path[0], path[1:]
        pruned = dict(node)
        if rest:
            pruned[head] = prune(node[head], rest)
        else:
            del pruned[head]
        return pruned

    for obj in objects:
        checked = prune(obj, FOREIGN_TEMPLATES.get(obj.get("kind"), ()))
        for path in find_markers(checked):
            errors.append(f"{object_id(obj)}: unrendered Helm action at {path.lstrip('.')}")

    # --- 7. one namespace only ----------------------------------------------------------------------
    namespaces = {(obj.get("metadata") or {}).get("namespace") for obj in objects}
    if len(namespaces) > 1 or None in namespaces:
        errors.append(
            f"objects span {sorted(str(n) for n in namespaces)} — chargo declares what ArgoCD should "
            "deploy and writes only into the ArgoCD namespace. A secret a workload needs belongs beside "
            "that workload: created by its chart, or committed as an ExternalSecret next to its manifests."
        )
        for obj in objects:
            ns = (obj.get("metadata") or {}).get("namespace")
            if ns != max(namespaces, key=lambda n: sum(1 for o in objects if (o.get("metadata") or {}).get("namespace") == n)):
                errors.append(f"    {object_id(obj)}")

    if errors:
        print("::error:: rendered manifest is invalid", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1

    kinds = {}
    for obj in objects:
        kinds[obj.get("kind")] = kinds.get(obj.get("kind"), 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
    print(f"OK — {len(objects)} objects ({summary}), documents correctly separated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
