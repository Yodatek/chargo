# Changelog

Notable changes to chargo. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the chart version follows [SemVer](https://semver.org).

Before 1.0.0, a breaking change may land in a minor version. The old key is removed rather than kept beside
the new one, and the entry below carries the migration note.

## Unreleased

### Added

- `hack/bootstrap.sh` — installs chargo into an ArgoCD instance with nothing but bash: no orchestrator, no
  Helm release to keep. It emits the three objects the chart cannot render for itself — the registration of
  the registry the chart is pulled from, the registration of the values repository, and the root
  Application. Output goes to stdout, so it is read before it is applied.
- Community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, this changelog, and issue and
  pull request templates.
- `home`, `sources` and `maintainers` in `Chart.yaml`, so `helm show chart` and chart registries point
  back at the project.
- `shellcheck` job in CI, guarding `hack/`.

### Changed

- README rewritten for readers outside the project that grew it: requirements, three documented install
  paths, and the `sourceType`, discovery and naming contracts that previously lived only in `values.yaml`.

### Fixed

- `hack/validate-render.py` accepts several files, so a glob over a `helm template --output-dir` tree is
  checked as one render — the by-name invariants need every AppProject and Application in the same pass.
  Its glued-separator check no longer fires on PEM blocks, which also end in three dashes.

## 0.1.0 — 2026-08-07

First release.

### Added

- Four dictionaries, referenced by name: `credentials`, `repositories`, `applicationsets`,
  `applications`. One values file renders every ArgoCD object of one platform.
- `ApplicationSet` + `Application` from one shared spec builder, with `sourceType` answering where the
  chart comes from: `registryChart`, `gitChart` or `directory`.
- One `AppProject` per project, built from the union of what every object bound to it needs.
- Credentials whose *shape* decides their delivery: all literals render a plain `Secret`, any
  `{key, property}` pointer renders an `ExternalSecret`. No strategy key to contradict.
- Recursive discovery with per-level value stacking, and two naming schemes — `path` and `basename`.
- Two deletion policies: `cascadeDelete` for a leaf leaving the content repository,
  `preserveResourcesOnDeletion` for an ApplicationSet leaving the values file.
- `hack/validate-render.py`, a parser that enforces what `helm lint` cannot see: document separators that
  actually separate, no duplicate object, every by-name reference resolving, and every rendered object
  landing in the ArgoCD namespace.
- CI on GitHub and GitLab rendering both example values files, and a release that publishes the chart to
  `oci://ghcr.io/yodatek/charts/chargo` plus a `.tgz` on the GitHub release.
