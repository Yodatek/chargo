#!/usr/bin/env bash
# Bootstrap chargo into an ArgoCD instance — emits the objects chargo cannot render for itself.
#
# A root Application must not be rendered by chargo: an object that manages the chart cannot be managed by
# the chart. Two registrations sit outside for the same reason — the registry the chart is pulled from, and
# the git repository holding the per-platform values file.
#
# Prints YAML on stdout and touches nothing else. Read it, then apply it:
#
#   hack/bootstrap.sh --platform int \
#     --values-repo https://github.com/acme/gitops.git \
#     --values-file platforms/int.yaml | kubectl apply -f -
#
# TRAP: with --values-repo-username the output carries a token. Pipe it, never redirect it to a file.

set -euo pipefail

ARGOCD_NAMESPACE=argocd
APP_PROJECT=default
CHART_REPO=ghcr.io/yodatek/charts
CHART_NAME=chargo
CHART_VERSION=
PLATFORM=
VALUES_REPO=
VALUES_REVISION=main
VALUES_USERNAME=
VALUES_FILES=()

usage() {
  cat <<'EOF'
Usage: bootstrap.sh --platform NAME --values-repo URL --values-file PATH [options]

Emits the ArgoCD objects that install chargo and keep it installed:

  Secret       registers the OCI registry the chart is pulled from
  Secret       registers the values repository          — only with --values-repo-username
  Application  the root Application: the chart, plus your values file

Required:
  --platform NAME            names the root Application (chargo-NAME). `global.platform` itself comes
                             from the values file, which stays the single source of truth.
  --values-repo URL          git repository holding the per-platform values files
  --values-file PATH         path of the values file inside that repository. Repeatable, last wins.

Options:
  --values-revision REV      git revision to track                    (default: main)
  --values-repo-username U   register the values repository with this account. Its token is read from
                             $CHARGO_VALUES_REPO_TOKEN. Omit for a public repository.
  --chart-repo REGISTRY      OCI registry holding the chart, no scheme (default: ghcr.io/yodatek/charts)
  --chart-version VERSION    chart version to pin                     (default: version in Chart.yaml)
  --argocd-namespace NS      namespace holding the ArgoCD objects      (default: argocd)
  --project NAME             AppProject the root Application belongs to (default: default). Name another
                             one where the `default` project has been narrowed.
  -h, --help                 this text

Example:
  hack/bootstrap.sh --platform int \
    --values-repo https://github.com/acme/gitops.git \
    --values-file platforms/int.yaml | kubectl apply -f -
EOF
}

die() {
  printf 'bootstrap: %s\n' "$1" >&2
  exit 2
}

need_value() {
  [ -n "${2:-}" ] || die "$1 needs a value"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --platform)             need_value "$1" "${2:-}"; PLATFORM=$2; shift 2 ;;
    --values-repo)          need_value "$1" "${2:-}"; VALUES_REPO=$2; shift 2 ;;
    --values-file)          need_value "$1" "${2:-}"; VALUES_FILES+=("$2"); shift 2 ;;
    --values-revision)      need_value "$1" "${2:-}"; VALUES_REVISION=$2; shift 2 ;;
    --values-repo-username) need_value "$1" "${2:-}"; VALUES_USERNAME=$2; shift 2 ;;
    --chart-repo)           need_value "$1" "${2:-}"; CHART_REPO=$2; shift 2 ;;
    --chart-version)        need_value "$1" "${2:-}"; CHART_VERSION=$2; shift 2 ;;
    --argocd-namespace)     need_value "$1" "${2:-}"; ARGOCD_NAMESPACE=$2; shift 2 ;;
    --project)              need_value "$1" "${2:-}"; APP_PROJECT=$2; shift 2 ;;
    -h|--help)              usage; exit 0 ;;
    *)                      usage >&2; die "unknown argument $1" ;;
  esac
done

[ -n "$PLATFORM" ]    || { usage >&2; die "--platform is required"; }
[ -n "$VALUES_REPO" ] || { usage >&2; die "--values-repo is required"; }
[ ${#VALUES_FILES[@]} -gt 0 ] || { usage >&2; die "--values-file is required"; }

# Default to the version of the chart this script ships with, so a clone bootstraps what it holds. Run
# standalone, there is no Chart.yaml to read and the version has to be given.
if [ -z "$CHART_VERSION" ]; then
  chart_yaml="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/Chart.yaml"
  [ -f "$chart_yaml" ] || die "no Chart.yaml beside this script — pass --chart-version"
  CHART_VERSION="$(awk '/^version:/ { print $2; exit }' "$chart_yaml")"
  [ -n "$CHART_VERSION" ] || die "no version in $chart_yaml — pass --chart-version"
fi

# A registration is what carries `enableOCI`, so ArgoCD reads the registry as OCI rather than as a classic
# Helm index. A public registry needs no credential.
cat <<EOF
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: repo-chargo-charts
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    app.kubernetes.io/managed-by: chargo
    argocd.argoproj.io/secret-type: repository
stringData:
  url: "${CHART_REPO}"
  type: "helm"
  name: "chargo-charts"
  enableOCI: "true"
EOF

# Block scalars, not quotes: a token may carry anything, and YAML would choke on the wrong quote character.
if [ -n "$VALUES_USERNAME" ]; then
  [ -n "${CHARGO_VALUES_REPO_TOKEN:-}" ] || die "CHARGO_VALUES_REPO_TOKEN is empty"
  cat <<EOF
---
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: repo-chargo-values
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    app.kubernetes.io/managed-by: chargo
    argocd.argoproj.io/secret-type: repository
stringData:
  url: "${VALUES_REPO}"
  type: "git"
  username: |-
    ${VALUES_USERNAME}
  password: |-
    ${CHARGO_VALUES_REPO_TOKEN}
EOF
fi

# The root Application. Two sources: the chart, and the values repository mounted as `$values` so the
# valueFiles below can point into it. A `ref` source declares neither chart nor path.
cat <<EOF
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: chargo-${PLATFORM}
  namespace: ${ARGOCD_NAMESPACE}
  labels:
    app.kubernetes.io/managed-by: chargo
    platform: ${PLATFORM}
  # No resources finalizer, on purpose: deleting this object must not prune a platform's ArgoCD objects.
spec:
  project: ${APP_PROJECT}
  destination:
    server: https://kubernetes.default.svc
    namespace: ${ARGOCD_NAMESPACE}
  sources:
    - repoURL: ${CHART_REPO}
      chart: ${CHART_NAME}
      targetRevision: "${CHART_VERSION}"
      helm:
        valueFiles:
EOF
for f in "${VALUES_FILES[@]}"; do
  # Double quotes with an escaped dollar: `$values` must reach ArgoCD as text, and single quotes here
  # would only trip shellcheck into reading it as a shell expansion.
  printf "          - \$values/%s\n" "$f"
done
cat <<EOF
    - repoURL: ${VALUES_REPO}
      targetRevision: ${VALUES_REVISION}
      ref: values
  syncPolicy:
    automated:
      selfHeal: true
      # An entry removed from the values file leaves its objects out-of-sync rather than deleting them.
      # Render the values file before committing, then prune deliberately.
      prune: false
EOF
