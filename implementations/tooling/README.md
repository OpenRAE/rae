# Development artifact policy

This directory is the reviewed, declarative authority for development artifact
identity, supported platforms, admission rules, GitHub Action sources, selector
bindings and inventory coverage. It is internal tooling policy, not an SDL
contract and not a second Python dependency resolver; `implementations/python/uv.lock`
remains the Python resolution authority.

Run the deterministic offline validator before acquiring a governed artifact:

```bash
RAES_REQUIREMENT_UID=GOV-913 implementations/python/.venv/bin/python tools/check_tooling_artifact_policy.py
```

Acquisition clients request an exact artifact, version, canonical platform and
profile through `tools/tooling_policy_gate.py`. The returned lock selection is
the only acquisition authority for source URLs and raw and installed digest/size
manifests. Source-snapshot raw manifests describe the reviewed upstream bytes;
their installed manifests describe the checked-in derived vocabulary snapshots.
The validator discovers Git-tracked workflow actions, selector literals and
acquisition surfaces, and fails closed when a relevant file cannot be parsed.
Runtime-selection consumers are derived from every tracked Python call rather
than trusted from the maintained binding list. Acquisition dispositions record
the exact discovered site count, so a new call in an already covered file is
still drift; dynamic process commands require an explicit disposition. Inert
fixture strings do not count as execution.

Manifest paths are normalized portable relative paths. Acquisition clients use
fixed or private temporary names, reject symlinked cache components and require
the selected archive member and cached executable to be regular files before
they can become trusted inputs.

Artifact and policy changes require independent review by the owner roles named
in each record. Native acquisition remains delegated to the owning client:
`uv` for Python, platform package managers for native packages, Docker or Podman
for OCI images, and the reviewed generic-client migration for release archives.
Never add credentials, executable hooks, shell fragments, mutable selectors or
unauthenticated-signature claims to these files.

The `legacy-remediation`, `external-service`, `excluded-domain`, and
`non-acquisition-execution` acquisition dispositions are explicit coverage
records, not claims that downstream migration work has already landed. The last
value records a dynamic command surface that is reviewed as execution but does
not acquire bytes. Owning issues are recorded on the corresponding inventory
rows.
