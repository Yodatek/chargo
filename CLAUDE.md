# Working on chargo

The workspace-level `CLAUDE.md` carries the general rules — English, KISS, no new discriminant, comments
without history. This file carries what is specific to this chart.

## What chargo is

A Helm chart that renders the ArgoCD objects of ONE platform from ONE values file: ApplicationSets,
Applications, AppProjects, repository credentials. It says **what ArgoCD should deploy and where to
authenticate**. It never says what runs inside a workload.

Four dictionaries, all referenced BY NAME: `credentials`, `repositories`, `applicationsets`,
`applications`. Every by-name lookup goes through a helper that `fail`s with the offending key, so a typo
stops the render instead of producing a half-wired object. Keep it that way — a silent default here becomes
a broken sync an hour later.

## The invariant

**Every rendered object lands in the ArgoCD namespace.** `hack/validate-render.py` enforces it.

A secret a workload consumes belongs beside that workload — created by its chart, or committed as an
ExternalSecret next to its manifests. Two reasons, and the second is the one that settles it: a glob
discovery (`raw/*`) cannot be enumerated at render time, so chargo could never reach a namespace it only
learns about at sync time.

## One key answers "where does the chart come from"

`sourceType` is `registryChart` | `gitChart` | `directory`. Three values, one question. A fourth shape
means a fourth value here, never a boolean beside it — a flag that only makes sense with some values of an
enum is the shape this contract is built to avoid.

Declaring `chartRepo` / `charts` / `chartVersion` under a type that does not read them is a hard error.
Silently ignoring them would let someone believe they steer a version that nobody reads.

There is no shape where a leaf file names its own registry chart. `Chart.yaml` already does that, with a
schema Helm defines and `helm dependency` understands, and it is not limited to one chart. A home-made
`app.yaml` carrying chart coordinates would be the same idea with a worse schema — and structurally capped
at one chart, since the `sources` list is fixed when Helm renders and ArgoCD's goTemplate cannot add
entries to it.

## Naming, and what it does NOT control

The directory tree names the **Application**. It does not name the workloads.

    App name   = <app>-<path with / replaced by ->     (naming: path)
                 <app>-<leaf directory>                (naming: basename)
    namespace  = <app>-<first path segment>

Inside a namespace, the objects an application chart creates are named from `global.app`, the component key and
`global.deploymentType`. So the rule that matters when several leaves share a namespace is:

> the pair (`global.app`, `global.deploymentType`) must be unique per leaf in a namespace.

Two leaves at different paths with the same pair overwrite each other's Deployments, Services and Secrets,
whatever their directories are called.

## Value stacking walks every level

    <shared>/<f>  <  dev/<shared>/<f>  <  dev/blue/<shared>/<f>  <  dev/blue/election/<f>

`discovery.depth` (4) is how many levels are emitted. The list of `valueFiles` is fixed at Helm render
time — ArgoCD cannot add entries — so each level is one entry carrying a goTemplate expression:

    {{ join "/" (slice .path.segments 0 (min 2 (len .path.segments))) }}

The `min` is load-bearing. For a leaf shallower than the level, it collapses the prefix onto the leaf path,
which yields a `<leaf>/<shared>` that does not exist and is skipped. Without it `slice` runs past the end
of `.path.segments` and the generator aborts — for every App, not just the shallow one.

## The two template layers

chargo is a Helm template that emits ArgoCD goTemplate. Both use `{{ }}`, and confusing them is the main
way to break this chart.

- **Emit goTemplate as a string literal.** `printf "%s-{{ .path.basename }}" $app` works because Go's lexer
  consumes a quoted string atomically. Never let Helm evaluate what ArgoCD should.
- **Never nest.** `{{ dig "namespace" "" . | default "{{ .path.basename }}" }}` is broken — the inner
  braces are text, not an expression. Build the fallback with goTemplate's own `printf`.
- **ArgoCD's goTemplate substitutes inside STRINGS only.** It walks the template struct and applies
  text/template to each string field; it cannot add or remove list items. Anything structural has to be
  decided by Helm, or by `templatePatch`.

## Verify by rendering, and mind two traps

```bash
helm template chargo . -f values.example.yaml --output-dir /tmp/out
python3 hack/validate-render.py /tmp/out/chargo/templates/*.yaml
```

- **Use `--output-dir`.** Piping `helm template` into another command gets truncated in some shells here,
  and a truncated stream looks exactly like a YAML error.
- **Watch the `---`.** A `-}}` right before it eats the newline, the separator glues to the previous line,
  and two objects silently merge into one document — the later overwriting the earlier. Invariant #1 of
  `validate-render.py` exists because that has shipped before.

Both `values.example.yaml` (literal credentials) and `values.example-external.yaml` (pointer credentials)
are rendered by CI. A change that touches the secret path must keep both green.
