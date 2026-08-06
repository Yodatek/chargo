![chargo — one values file, every ArgoCD object of a platform](docs/banner.svg)

Renders the ArgoCD objects of **one platform** from **one values file**: ApplicationSets, Applications,
AppProjects and repository credentials.

```bash
helm template chargo . -f values.example.yaml | python3 hack/validate-render.py
```

That command is the point of the chart. What a platform will receive is readable and checkable on a laptop,
offline, without a vault password, an inventory or a cluster.

## What it replaces

The `argocd-app` Ansible role rendered the same objects from `vars/gitops/<platform>/<app>/gitops.yaml`,
one playbook run per app. chargo keeps the resolved shape of those manifests and moves the templating from
Jinja to Go, which buys four things:

- **one file per platform** instead of one directory per app, with the common part in the chart;
- **`helm lint` + `helm template` + a parser in CI**, on every merge request;
- **one AppProject per project**, built from the union of what every object bound to it needs — where the
  role upserted a whole AppProject per app and the last one applied overwrote the others' allowances;
- **ArgoCD delivers the chart itself** — Ansible creates one root Application pointing at it, and adding an
  ApplicationSet afterwards is a commit in the values repository, never a playbook replay.

## Values

Four dictionaries, referenced by name — [values.yaml](values.yaml) is the full contract.

| Key | Answers | Rendered as |
| --- | --- | --- |
| `credentials.<name>` | who we are on the forge / the registry | material inside the objects below |
| `repositories.<name>` | which URL, registered once in ArgoCD | `Secret` labelled `argocd.argoproj.io/secret-type` |
| `applicationsets.<name>` | N Apps discovered from a repository | `ApplicationSet` + its `AppProject` |
| `applications.<name>` | ONE App, one path | `Application` + its `AppProject` |

Four dictionaries and nothing else: chargo says what ArgoCD should deploy and where to authenticate. What
gets deployed is the content repositories' business, and so is anything those workloads need.

The indirection is deliberate: a token rotates in one place, and a repository is registered once however
many objects read it. A reference that resolves to nothing stops the render with the offending key named.

`ApplicationSet.spec.template.spec` and `Application.spec` are the same object, so both dictionaries share
one spec builder. What an Application lacks is the generator — `path` replaces the `discovery` block.

Every entry is merged over `objectDefaults`, so it declares only what differs:

```yaml
applicationsets:
  wetemp:
    project: wetemp
    contentRepo: content-wetemplates
    chartRepo: we-chart
    chartVersion: "3.0.0-1"
    discovery:
      include: [dev, test]
```

## Credentials

Each field is **either a literal string or a pointer** into the secret store. The shape decides how the
credential is delivered; there is no strategy to declare alongside it, and therefore nothing that can
contradict it.

```yaml
credentials:
  gitlab-forge:
    username: CAPTAIN_RIMAFLOWA          # an account name is not secret
    password:                            # its token is
      key: /static-secrets/data/devsecops/int
      property: GITLAB_FORGE_PASSWORD    # optional, defaults to the field name
```

| the credential is | chargo renders | the values file |
| --- | --- | --- |
| all literals | a plain `Secret` | carries the material, so it is SOPS-encrypted — and the repo-server needs a decryptor to read it |
| any pointer | an `ExternalSecret` | carries no material, so it can live in clear in git |

Mixing is the normal case, and it is what the example above does: the rendered ExternalSecret writes the
username as a literal in its target template and fetches only the password.

The second row is what lets ArgoCD render this chart with **no SOPS decryptor in its repo-server** — and
it is also what makes a token rotation a Vault write rather than a commit plus a redeploy.

A pointer carries external-secrets' own field names, so it transposes to a `remoteRef` unchanged: `key` is
the entry in the store, `property` the field inside it. The store itself is named by
`global.externalSecretStoreRef` and must exist — `kubectl get clustersecretstores`.

### chargo writes only in the ArgoCD namespace

It renders no secret a workload consumes. That secret belongs beside the workload, declared by whatever
the workload itself is declared with:

| the workload is | its secret is |
| --- | --- |
| a we-chart release | created by we-chart from its own `global.pullSecrets` |
| an upstream chart | created by a sibling we-chart directory declaring the same `namespace:` |
| raw YAML | an `ExternalSecret` committed next to the Deployment — a pointer, not the material, so it needs no SOPS decryptor to sit in git |

Beyond ownership there is a structural reason: a glob discovery (`raw/*`) cannot be enumerated at render
time, so chargo could never reach a namespace it only learns about at sync time. Whatever runs inside that
namespace always can.

`hack/validate-render.py` enforces the boundary — every rendered object must land in one namespace — so it
cannot regress unnoticed.

## Deletion

Two different deletions, two keys in `global`, both overridable per object.

`cascadeDelete` — a **leaf** disappears from the content repository. The generated App carries the
resources finalizer and its workloads are pruned. Normal GitOps behaviour, and the default inside an
ApplicationSet. A standalone Application is deleted when its **values entry** disappears, which is an ops
edit rather than a content change, so it carries no finalizer unless asked.

`preserveResourcesOnDeletion` — the **ApplicationSet itself** disappears, because its entry left the values
file. An ApplicationSet owns its Applications, so a mistyped key would otherwise take a platform's workloads
with it. `true` by default, stopping the cascade at the Applications.

The root Application syncs with `prune: false`, so a removed entry leaves its objects out-of-sync rather
than deleting them. `helm template` the values file before committing, and prune deliberately.

## Bootstrap

Whoever installs the chart needs credentials the chart itself renders — so two objects stay outside it: the
registration of the chargo registry, and of the repository holding the per-platform values.
`playbooks/deploy-chargo.yaml` owns them, plus the one root Application that points here.

A root Application must not be rendered by chargo: an object managing the chart cannot be managed by the
chart.
