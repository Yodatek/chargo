# Contributing to chargo

Thanks for being here. This file is short on purpose.

Upstream is [github.com/Yodatek/chargo](https://github.com/Yodatek/chargo). Any other copy of this
repository is a mirror, kept in step by pushing the same commits to both. Open your change upstream and
merge it there — a commit landed only on a mirror makes the two diverge.

## Set up

```bash
git clone https://github.com/Yodatek/chargo.git
cd chargo
pip install pyyaml          # hack/validate-render.py needs it
```

Helm 3.8 or later. No cluster, no credentials, no vault password: everything below runs on a laptop.

## The loop

Render, then read the output. Never reason about what a template produces.

```bash
helm lint . -f values.example.yaml
helm template chargo . -f values.example.yaml --output-dir /tmp/out
python3 hack/validate-render.py /tmp/out/chargo/templates/*.yaml
```

Both examples must pass, and they are not interchangeable: `values.example.yaml` carries literal
credentials, `values.example-external.yaml` carries pointers, and the two go through different branches of
every secret-bearing template. A change touching the credential path must keep both green.

Two traps worth knowing before they cost you an hour:

- **Use `--output-dir`.** Piping `helm template` into another command gets truncated in some shells, and a
  truncated stream looks exactly like a YAML error.
- **Watch the `---`.** A `-}}` right before it eats the newline, the separator glues to the previous line,
  and two objects silently merge into one document — the later overwriting the earlier. Invariant #1 of
  `hack/validate-render.py` exists because that has shipped to production before.

`hack/bootstrap.sh` is plain bash with no dependencies. Keep it that way, and keep it
[shellcheck](https://www.shellcheck.net)-clean.

## What CI checks

Every push and every pull request: `helm lint`, `helm template` and `hack/validate-render.py`, for both
example values files. Plus two guards — `shellcheck` on `hack/`, and a rerun of `docs/build-logo.py` that
fails if the committed SVGs drifted from the generator. Edit the generator, never its output.

## Design rules

The chart is read far more often than it is written, usually by someone debugging at the wrong hour.

- **No new discriminant.** Do not add a key whose only job is to select between two behaviours when one
  behaviour would do. If a shape can decide instead of a flag, let the shape decide — that is why a
  credential is a string or an object, with no `secretStrategy` beside it to contradict it.
- **Stay in ArgoCD's vocabulary.** The chart produces ArgoCD objects, so it uses ArgoCD's words for them; a
  pointer into a secret store uses external-secrets' `key` and `property`, not synonyms. A renamed field is
  a translation table the reader has to carry.
- **One obvious way.** When a second mechanism overlaps the first, remove the first.
- **Uniform beats clever.** N explicit entries that all look alike beat one entry that quietly covers the
  others by prefix or convention. The explicit version is greppable and diffable.
- **Fail loudly.** Every by-name lookup goes through a helper that `fail`s with the offending key. A silent
  default here becomes a broken sync an hour later.
- **Comments state purpose and traps**, never history. "This used to be…" belongs in `git log` and in the
  changelog.

Everything — files, comments, commit messages, identifiers — is written in English.

## Commits and pull requests

[Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`, `refactor:`,
`ci:`, `chore:`. One idea per commit.

Before opening a pull request:

- [ ] both example values files render and validate
- [ ] `hack/bootstrap.sh` still passes `shellcheck`, if you touched it
- [ ] new or changed keys are documented in `values.yaml`, where the contract lives
- [ ] an entry added under `## Unreleased` in [CHANGELOG.md](CHANGELOG.md)
- [ ] `version` in `Chart.yaml` left alone — bumping it on `main` IS the release, so maintainers do it

A breaking change is acceptable. Remove the old key rather than keeping both, and say so in the changelog
entry.

## Reporting a bug

Open an issue with the rendered output, not a description of it. `helm template` is deterministic and runs
without a cluster, so the manifest you got and the manifest you expected settle almost every question in
one round trip. Redact credentials.

A security problem goes to [SECURITY.md](SECURITY.md) instead, never to a public issue.

## Licensing

By contributing, you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE), the same terms as the project.
