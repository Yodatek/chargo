## What this changes

<!-- One paragraph. The conclusion first. -->

## Rendered output

<!--
Paste the part of the manifest that changed — the before and the after. Reasoning about a template is not
evidence; a rendered object is.
-->

```yaml

```

## Checklist

- [ ] both example values files render and validate:
      `helm template chargo . -f values.example.yaml --output-dir /tmp/out && python3 hack/validate-render.py /tmp/out/chargo/templates/*.yaml`
      (and the same with `values.example-external.yaml`)
- [ ] `shellcheck hack/*.sh` passes, if I touched a script
- [ ] new or changed keys documented in `values.yaml`, where the contract lives
- [ ] entry added under `## Unreleased` in `CHANGELOG.md`
- [ ] `version` in `Chart.yaml` untouched — maintainers bump it when cutting a release
- [ ] everything written in English

<!-- A breaking change is fine. Remove the old key rather than keeping both, and say so in the changelog. -->
