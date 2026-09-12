# Development artifact policy

This directory is the reviewed, declarative authority for development artifact
identity, supported platforms, admission rules, GitHub Action sources, selector
bindings, host/bootstrap profiles, qualification records and inventory coverage.
It is internal tooling policy, not an SDL contract. The project lock remains
the runtime/development/docs resolution authority; `python/uv.lock` separately
owns the complete verification-tool and build-backend graph.

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
Runtime-selection consumers are derived from every tracked Python call and
every action-transitive artifact reference rather than trusted from the
maintained binding list. Acquisition dispositions record
the exact discovered site count, so a new call in an already covered file is
still drift; dynamic process commands require an explicit disposition. Inert
fixture strings do not count as execution.

Manifest paths are normalized portable relative paths. Acquisition clients use
fixed or private temporary names, reject symlinked cache components and require
the selected archive member and cached executable to be regular files before
they can become trusted inputs.

Artifact and policy changes require independent review by the owner roles named
in each record. Native acquisition remains delegated to the owning client:
`uv` and the frozen Python tooling client for Python, platform package managers
for native packages, Docker or Podman for OCI images, and the reviewed
generic-client migration for release archives.
Never add credentials, executable hooks, shell fragments, mutable selectors or
unauthenticated-signature claims to these files.

## Python tool, build, and smoke closures

`python/pyproject.toml` and `python/uv.lock` pin Nox, pre-commit, Ruff,
check-jsonschema, pytest, the reviewed uv 0.12.4 executable package, the
cryptography fixture dependency used by T08, and every transitive tool
dependency. The separate `build` group pins Hatchling.
`python/build-constraints.txt` is the generated, hash-complete isolated-build
projection. Target-specific requirements and raw wheel manifests under
`python/smoke/` are generated from the project or tool lock and checked
byte-for-byte by the tooling policy gate. Tool manifests include both the
default tool graph and the build group so a fresh offline cache can create the
tool environment and isolated build environment from the same verified raw
wheelhouse.

Regenerate and verify those projections with the frozen tooling environment:

```bash
uv run --project implementations/tooling/python --frozen --no-default-groups python tools/generate_python_closures.py
uv run --project implementations/tooling/python --frozen --no-default-groups python tools/generate_python_closures.py --check
```

Callers select a closed `python_closure_profile_id`; they do not supply package
lists, index arguments, or environment overlays. Public, enterprise
mirror-only, and offline contexts are distinct. Mirror policy stores only a
credential reference and accepts one credential-free HTTPS locator through
`RAES_PYTHON_MIRROR_URL`; public fallback is prohibited. Offline installation
first verifies that the wheelhouse contains exactly the named regular files at
the recorded sizes and SHA-256 digests.

The supported project closure tuples are Linux x86_64 on CPython 3.11–3.14,
Linux arm64 on CPython 3.14, and macOS arm64 on CPython 3.14. macOS x86_64 has a
tool-and-build closure, including the reviewed universal cryptography wheel for
the T08 fixture, but no project all-extras closure: the current project lock has
no compatible cryptography wheel, and ambient source fallback is not admitted.
A new tuple requires a lock/export/profile update and qualification evidence.

These locks make dependency selection repeatable. They do not claim that wheel
builds are byte-for-byte reproducible across host SDKs, compilers, operating
systems, or build times. Candidate wheel and sdist builds therefore run outside
the checkout and are recorded by digest.

## GitHub Action admission

`actions-policy.json` v2 has three independent planes: exact action source
revisions, their closed payload/host/service dependency graph, and every
workflow job plus action use site. A use-site record binds the literal `with`
inputs to its effective event/ref trust classes, permissions, credential
classes, fixed runner profile, allowed origins, and cache/artifact role.
Security-relevant input defaults and cache, artifact, and credential effects
are declared on sources rather than inferred from action names. Each applicable
transitive payload and host capability must join every concrete matrix runner
profile at the use site. Composite-action dependencies have their own source
revisions. External
service inputs use reviewed, dated exceptions; an exception is a bounded
nonclaim and never substitutes for a payload digest.

The validator safely parses every tracked workflow, rejects YAML aliases and
duplicate keys, evaluates a closed boolean condition grammar without substring
trust shortcuts, accounts for workflow permission and environment inheritance,
propagates caller trust into local reusable workflows, and checks their input
and permission ceilings. Remote reusable workflows are rejected until they have
a complete source/use-site model. Candidate jobs cannot hold write
permissions, enterprise secrets, OIDC, trusted cache/artifact roles, or
publication authority. Checkout credential persistence and cache behavior are
closed source input contracts. The policy compares the complete Dependabot
configuration so extra update streams, empty groups, schedule changes, or a
changed `z3-solver` exclusion cannot escape admission.

This repository check executes after GitHub fetches an action. GitHub's action
allow policy, branch/ruleset protection, and environment protection remain
required hosted controls; the JSON policy cannot replace them. Live services
are unavailable offline and must be reported unevaluated rather than simulated.

## Bootstrap and host qualification

The v2 development-profile document keeps artifact selection and host policy
separate. A host profile joins a canonical platform to locked CPython and uv
payloads, native repository and image trust references, capability ids, a
credential-free payload kit and bounded T01/T02/T03/T08/T12 records. The kit
records native packages and trust roots as host prerequisites rather than
claiming they are archive contents.
Qualification compares the declared hosted-image family and architecture with
runner-provided `ImageOS` and `RUNNER_ARCH`, validates `ImageVersion`, and
records the exact observed release. The native package set inherits that
observed image identity; missing or mismatched runner metadata makes
qualification fail.
An action commit identifies orchestration code; it never identifies the Python
or uv bytes selected by that action. Standard CPython 3.11–3.14 payloads are
blocking. The separately locked 3.14t payload remains advisory.

Use the fixed inspection surface for a reviewed host profile:

```bash
implementations/python/.venv/bin/python -m tools.bootstrap_profile inspect-profile public-ubuntu-24.04-x86_64
```

Inspect the native prerequisites and immutable repository identity with

```bash
implementations/python/.venv/bin/python -m tools.bootstrap_profile setup-plan public-ubuntu-24.04-x86_64
```

The setup plan refuses to invoke an ambient package manager because a package
name does not bind the declared repository snapshot, trust root, or maintainer
scripts. Provision the reviewed base image or a complete verified native bundle,
then use `inspect-profile`; this repository does not execute `sudo`, a shell, a
remote installer, or an unreviewed repository/key. Ubuntu 22.04's stock curl
7.81 does not satisfy the
unknown-length `--max-filesize` behavior floor; a generic-acquisition profile
must use an admitted client from its reviewed image or offline kit and otherwise
fails. The proof profile remains useful on Ubuntu 22.04 because it keeps curl
outside that profile's admitted capabilities and preserves Bubblewrap network
isolation, fonts/fontconfig and `C.UTF-8` as hard prerequisites.
Canonical verification therefore fetches the four generic-tool raw objects in
a same-run Ubuntu 24.04 preparation job, carries only those lock-verified bytes
to the proof job, and admits them through each installer's explicit local-input
path. The Ubuntu 22.04 proof host never treats its stock curl as a generic-tool
acquisition capability.

`bootstrap-qualification.yml` executes the four locked generic tools on Linux
x86_64/arm64 and macOS x86_64/arm64, runs the maintained curl against controlled
TLS, redirect, retry, disconnect, deadline and unknown-length size fixtures,
exports exact raw uv/CPython objects plus an installed managed interpreter, uv,
target-specific raw Python wheelhouses and the four generic tools. It measures
every kit entry, deletes the seeded copies, restores the target-specific
archive, verifies raw and installed identities, disables uv downloads and
network fallback, recreates environments from the verified wheels, then repeats
the frozen Python and tool checks. Linux arm64 and macOS arm64 bind that clean
restore to T12; all four platforms bind their tool/ABI run to T02.
Native packages and trust roots remain reviewed base-image prerequisites. The
workflow retains the bounded result and payload-kit artifacts under the exact
workflow commit. Public profiles contain no credential reference; enterprise
variants may carry reference ids only.

The `legacy-remediation`, `external-service`, `excluded-domain`, and
`non-acquisition-execution` acquisition dispositions are explicit coverage
records, not claims that downstream migration work has already landed. The last
value records a dynamic command surface that is reviewed as execution but does
not acquire bytes. Owning issues are recorded on the corresponding inventory
rows.
