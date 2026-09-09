# Security policy

## Reporting a vulnerability

Report it privately, never in a public issue.

Open a private report on GitHub: **[Security → Report a
vulnerability](https://github.com/Yodatek/chargo/security/advisories/new)**. Only the maintainers can read
it. Expect an acknowledgement within a week.

Include the values file that triggers the problem — redacted — and the rendered output. `helm template`
runs without a cluster, so a reproduction is usually two commands and settles the question in one round
trip.

## Supported versions

Before 1.0.0, only the latest release is supported. Fixes land on `main` and go out in the next tag.

| version | supported |
| --- | --- |
| latest release | yes |
| anything older | no — upgrade |

## In scope

- A render that puts credential material where it does not belong — outside the ArgoCD namespace, in a
  plain `Secret` where a pointer was declared, or in an object that should carry no material at all.
- An `AppProject` that grants more than the objects bound to it need.
- A by-name reference resolving silently instead of failing, wiring an object to the wrong repository or
  the wrong credential.
- Anything in `hack/bootstrap.sh` that writes a token to disk, to the process list, or to a log.

## Out of scope

- Vulnerabilities in ArgoCD, Helm or external-secrets themselves. Report those to their own projects.
- Secret material committed to your own repositories. That is what SOPS encryption and pointer credentials
  are for — see [Credentials](README.md#credentials).
- Your cluster's RBAC, your ArgoCD instance's exposure, your forge's token scopes.

## Two things worth knowing before you deploy

**A literal credential ends up in the rendered manifest.** All-literal credentials render a plain `Secret`,
so the values file carries the material and must be encrypted at rest, and the ArgoCD repo-server needs a
decryptor to read it. A pointer credential renders an `ExternalSecret` instead: no material in git, and no
decryptor needed.

**`hack/bootstrap.sh` prints a token when you give it one.** It reads the token from the environment and
writes it to stdout inside a `Secret`. Pipe that output to `kubectl`; never redirect it to a file.
