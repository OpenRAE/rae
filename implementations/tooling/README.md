# Development tooling inputs

## Authority and ownership

This directory holds internal development input identity, not portable SDL
contracts. [MAINTAINERS.md](../../MAINTAINERS.md) identifies the one accountable
maintainer. Historical Tooling/Security/Release labels describe responsibilities,
not independent reviewers or a mandatory deputy.

- `artifacts.lock.json` owns tool/bootstrap versions, raw hashes/sizes and
  installed identities. `tools/tool_versions.py` and literal selector bindings
  are checked projections, not alternate authorities.
- Project and tooling `pyproject.toml`/`uv.lock` pairs own Python resolution.
  The tooling `build` group owns the backend; generated constraints and
  project-target smoke manifests are checked projections.
- Native workflows and Dependabot configuration own their settings. Focused
  checks cover action pins, reusable input contracts, publishing permissions
  and PR credential boundaries without a second workflow model.
- `admission-policy.json` keeps reviewed identity rules and denied digests;
  it does not introduce a status/revocation service.

Acquisition selectors validate their owning bounded, duplicate-free documents
and selected dependencies. They do not run the complete repository evaluator.
The explicit check remains:

```shell
RAES_REQUIREMENT_UID=GOV-913 implementations/python/.venv/bin/python tools/check_tooling_artifact_policy.py
```

No inventory-site counts or global qualification hashes need renewal after an
ordinary change. Maintained curl, uv, Docker/Podman and signed native package
sources own acquisition; no custom HTTP stack or live checksum discovery is
permitted. Errors are bounded and must not echo candidate URLs or credentials.

## Connected setup and Python environments

Follow [CONTRIBUTING.md](../../CONTRIBUTING.md). Sync the separate project and
tooling environments from their frozen locks. Basic tooling does not require
the TLS certificate-generation fixture dependency. Run real acquisition tests
with the optional group:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups --group acquisition-tests python -m pytest implementations/python/tests/test_issue_1217_bootstrap_profiles.py -m integration -k real_curl
```

Regenerate build constraints and project smoke projections after reviewed lock
changes:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups python tools/generate_python_closures.py
uv run --project implementations/tooling/python --frozen --no-default-groups python tools/generate_python_closures.py --check
```

Installed wheel/sdist smokes keep exact candidate bytes and hash-pinned
dependencies outside the checkout. A verified local smoke wheelhouse is a test
input, not support for complete disconnected development. Enterprise/offline
package contexts and redundant tool-wheelhouse manifests are retired.

Project smoke targets remain Linux x86_64 CPython 3.11–3.14, Linux arm64 CPython
3.14 and macOS arm64 CPython 3.14. Separating the TLS fixture does not restore
Intel Mac support: #1268's patched runtime dependency/binary-closure limitation
still needs a tested resolution. No vulnerable pins or new platform claims are
introduced. Frozen resolution does not imply bit-reproducible native builds.

## Hosts, containers and private installations

Host profiles list bootstrap payloads and native capability prerequisites.
Inspect them with `python -m tools.bootstrap_profile setup-plan <host-profile>`
or `inspect-profile <host-profile>`. Setup-plan reports prerequisites; it does
not run privileged package commands. Install native prerequisites through
trusted signed sources. Generic transfers require curl 8.4.0 or newer; the
proof archive can be carried from a suitable acquisition host to its isolated
Ubuntu 22.04 proof host.

The optional [development container](../../docs/explain/development-container.md)
uses a digest-pinned base, signed ordinary Ubuntu repositories and a non-root
account. Dockerfile/devcontainer configuration owns native setup, not a full
parallel policy model. Relevant changes/manual runs qualify the components;
ordinary unrelated application edits do not regenerate/restore offline kits.

Private tool/proof caches retain no-follow ownership checks, bounded extraction,
complete identity checks, locks, atomic publication and crash recovery. Shared
immutable seed import and filesystem-type allowlists are removed. Actual
filesystem operation failures remain terminal. Full proof-tree hashing stays:
the cache owner can modify read-only files, so a marker or metadata shortcut
cannot establish content integrity. The proof sandbox is unchanged.

The release container lane directly pulls the locked digest and checks the
daemon's platform/content identity. Unique concurrent-run names and teardown
remain; mirror/pre-seeded distribution and mandatory OCI export/import do not.
The connected AWS smokes preserve verified VM/bootstrap bytes and SSH identity
without staging a complete Python wheelhouse or requiring native snapshots.

## Release evidence and current scope

Standard SBOM/provenance, producer identity, exact release SHA and tested
output hashes remain. Build inputs read the native release/reusable workflows.
#1227 owns ordinary same-byte publication recovery; #684 owns real publication
acceptance. No distribution service, independent-copy backup, deputy,
service-load, retention/GC service or blanket release gate is introduced.
See the [current design scope](../../docs/decisions/package-artifacts/README.md).
