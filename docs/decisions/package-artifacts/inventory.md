# Acquisition and publication inventory

## Method and boundary

Baseline: `5d2f738f`, inspected 2026-09-05. The survey covered all tracked
workflow/configuration files, Nox helpers, repository tools, package/build
hooks, integration fixtures, live-runner scripts, documentation setup and
publication guidance. Searches covered download/network calls, client commands,
package installation, action references, caches, uploads and release commands.
The complete open-issue list was also reviewed for development/delivery work.

Rows aggregate instances only when they share an owner, trust boundary and
disposition. In the tables, **managed input** means retained, integrity-admitted
bytes needed to develop/test/build; **managed output** means bytes published
or retained as durable admission evidence; **derived** means disposable output;
**external service** means a live API rather than a package; **domain** means
outside this architecture. A cache never becomes an integrity authority.

The current accountable repository maintainer is
[Brad Edwards](../../../MAINTAINERS.md). The roles below identify the owning
responsibility within that maintainership, not additional staff or an existing
enterprise service team: **Tooling** maintains Nox/setup and developer clients; **Security**
reviews integrity, vulnerability and credential policy; **Proof** owns solver
and theorem-tool qualification; **Release** owns builds, artifacts and publishing;
**Docs** owns documentation delivery; **Backend** owns live verification;
**Platform** owns enterprise runners, storage and mirrors; **Semantics** owns
reference vocabularies. Activation requires a named primary and deputy in the
operational ownership record; an enterprise site's Platform owner is appointed
by that site. Repository maintainers approve authority changes.

Availability classes: **R** required verification/build/publication, hard failure
on unavailable input; **L** local optional lane, explicit skip permitted only
where already documented; **N** network-dependent freshness/reporting job,
reported separately and never relabeled as passed offline. Promotion must retain
the complete closure of every R input, including tools needed to acquire it.

## Inputs and bootstrap

| ID / class | Current surface and consumers | Owner | Selection and trust root now | Availability and duplication / target disposition |
|---|---|---|---|---|
| I01 managed input | [`pyproject.toml`](../../../implementations/python/pyproject.toml), [`uv.lock`](../../../implementations/python/uv.lock); runtime, dev, docs extras; Nox frozen sync/run | Tooling + Security; Proof for Z3 | Reviewed lock includes registry artifacts/hashes; dependency declarations have ranges. Z3 4.16.0.0 is governed by a solver profile | R. Keep uv resolution and reviewed hashes. Mirrors supply the same bytes. Do not let automated updates change the solver profile implicitly |
| I02 managed input | [`tool_versions.py`](../../../tools/tool_versions.py), [`runner.py`](../../../tools/nox_support/runner.py), Makefile, hooks, workflows; Nox 2026.4.10, pre-commit-hooks 6.0.0, Ruff 0.15.9, check-jsonschema 0.37.1 | Tooling | Top-level `uv tool run --from` specs are pinned; transitive tool environments are separately resolved and not covered by the project lock | R. Lock complete tool environments, including Nox's uv extra. Remove repeated literal authorities; keep generated/cross-checked entry-point references |
| I03 managed input | `build-system.requires = ["hatchling"]`, `uv build`, [`hatch_build.py`](../../../implementations/python/hatch_build.py), [`test_corpus_packaging.py`](../../../implementations/python/tests/test_corpus_packaging.py), compatibility and release smokes | Release + Tooling | Editable project lock does not fully freeze isolated build dependencies; smoke `uv pip install` can resolve runtime dependencies again | R. Add hashed build constraints and an admitted smoke wheelhouse; same constraints for sdist-to-wheel build, local tests, CI and release |
| I04 managed input / bootstrap | `actions/setup-python`, `astral-sh/setup-uv` in workflows; local developer instructions; `.readthedocs.yaml` | Tooling + Docs | Action source SHAs are pinned; Python requests are minor-series versions; uv action has no explicit uv version. Local/RTD bootstrap is platform supplied | R. Record exact qualified interpreter builds and uv binaries separately from action SHAs. CPython 3.11–3.14 supported by project metadata; 3.14t is an advisory preview, not release qualification |
| I05 managed input | [`conftest_tool.py`](../../../tools/policy/conftest_tool.py); repository policy | Tooling + Security | Conftest 0.68.0; HTTPS release and `checksums.txt` fetched together; any existing cache path is reused | R. Move every platform digest into reviewed lock; replace transport and validate installed cache content |
| I06 managed input | [`gitleaks_tool.py`](../../../tools/gitleaks_tool.py); hygiene and hooks | Tooling + Security | Gitleaks 8.30.1; same-origin live checksum metadata; existence-only cache hit | R. Same migration as I05; license/redistribution review includes full release archive |
| I07 managed input | [`vale_tool.py`](../../../tools/vale_tool.py); docs style | Docs + Tooling | Vale 3.15.2; reviewed archive SHA-256 table; dedicated install/cache code; old `errata-ai` release locator | R for docs. Retain digests, review canonical upstream relocation, verify extracted executable and atomic cache admission |
| I08 managed input | [`osv_scanner_tool.py`](../../../tools/osv_scanner_tool.py); supply-chain lane | Security + Tooling | OSV Scanner 2.4.0; reviewed binary digests, per-use type/mode/hash checks, bounded hashing and atomic installation | R in its required lane. Preserve these stronger controls when sharing local admission; remove only its custom acquisition dependency |
| I09 managed input | [`isabelle_tool.py`](../../../tools/isabelle_tool.py); participant opacity proof | Proof + Tooling | Isabelle2025-2 Linux archive, reviewed hash and exact 1,228,480,874-byte size, two official locators. Installed tree checked using marker/executable presence | R on Linux x86_64. Archive download/fallback and `.download` path are bespoke. Replace transport; preserve sandbox/resources; validate installed tree or reconstruct it from admitted archive |
| I10 managed input / bootstrap | `canonical-verification.yml`: apt bubblewrap, fontconfig, fonts-dejavu-core; system locale, CA certificates, curl, Git, shell/coreutils and platform Python | Platform + Proof + Tooling | Hosted Ubuntu image plus native package repository signing roots; apt packages are not version-locked | R for proof/bootstrap. Record runner-image identity, package snapshot and qualification; ship/pre-seed native dependencies for disconnected Linux proof |
| I11 managed input | [`test_reference_backend_docker_integration.py`](../../../implementations/python/tests/test_reference_backend_docker_integration.py); Docker/Podman test fixture and release container job | Backend + Release | Reviewed multiarch Alpine digest `sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc`; runtime pulls unconditionally | R for release, L for ordinary PR/local. Preserve #1110 fail-closed mode; add mirror/import support and verify both index and selected platform graph. Fixed test workspace names need concurrent-run isolation |
| I12 managed input / bootstrap | Docker/Podman daemon and CLI, libvirt/QEMU tools; [`tools/real-daemon/`](../../../tools/real-daemon/README.md) | Backend + Platform | Hosted runtime or host-installed native packages; daemon features and privileges are external prerequisites | R when selected, otherwise L. Publish a tested host profile, exact native package/base-image inventory and capability checks; no claim that downloading a CLI supplies a daemon |
| I13 managed input | [`run_aws_smoke.sh`](../../../tools/real-daemon/run_aws_smoke.sh), [`run_aws_guest_certify.sh`](../../../tools/real-daemon/run_aws_guest_certify.sh); AWS AMI/user-data, apt, CirrOS 0.6.2 image, uv bootstrap, libvirt-python | Backend + Platform | Script AMI/version choices; CirrOS lacks a reviewed digest and download failure is suppressed; remote uv uses `curl ... | sh`; uv sync/libvirt-python installation not fully frozen | L, R only for explicitly selected live certification. Replace pipe-to-shell bootstrap, pin VM image and native/build closure, remove suppressed acquisition errors; AWS identity/network setup stays an external service |
| I14 managed input | [`check_attack_tactic_vocabulary.py`](../../../tools/check_attack_tactic_vocabulary.py), [`check_atlas_tactic_vocabulary.py`](../../../tools/check_atlas_tactic_vocabulary.py), [`check_nist_csf_defensive_vocabulary.py`](../../../tools/check_nist_csf_defensive_vocabulary.py), [`check_autonomous_behavior_vocabularies.py`](../../../tools/check_autonomous_behavior_vocabularies.py); remote verification of ATT&CK v19.1, ATLAS 2026.06, NIST CSF 2.0, W3C ActivityStreams and FIPA source artifacts | Semantics + Security | Five checked-in source snapshots with source-specific raw or canonical digest meanings; opt-in urllib fetch and parser/normalization logic | Local snapshot checks R; remote comparison N. Retain each incumbent digest meaning; add a distinct raw-byte identity only where the current digest is canonical/semantic, retain source bytes for reproducible refresh, and replace network acquisition only |
| I15 managed input | `.vale.ini`, `styles/RAES/`, docs static examples; contract corpus in wheel/sdist | Docs + Semantics + Release | Reviewed Git content; no external Vale style package/sync configured. Corpus authority stays in `contracts/` | R. Include in source closure and output corpus checks. Do not invent a style downloader or make the distribution copy normative |
| I16 managed input | Source checkout, action source trees, reusable workflow definition; Git CLI and GH CLI used by policy/release jobs | Tooling + Release | Commit SHAs; current checkout source/action refs; hosted `gh` and Git versions supplied by runner image | R online CI. Lock source/workflow identity and bootstrap tools; preserve Git history required for exact SHA/ancestry. Offline source exports need a Git bundle or equivalent verified history, not just an unbound source ZIP |

## Actions, workflows and dependency maintenance

Every workflow under [`.github/workflows/`](../../../.github/workflows) was
inspected: `canonical-verification`, `ci`, `release-please`, `docs`,
`python-free-threaded-preview`, `scorecard`, `pr-title-lint`, `pr-body-policy`,
and `post-merge-closing-issue-audit`. There are no externally referenced reusable
workflows in this baseline; the local canonical workflow inherits the selected
repository revision. These are managed executable inputs, even when their
outputs are disposable.

| ID | Complete action family | Owner / consumers | Trust and target disposition |
|---|---|---|---|
| A01 | `actions/checkout`, `actions/setup-python`, `astral-sh/setup-uv` | Tooling; all setup jobs | Full source SHAs in workflow. Review action code plus fetched Python/uv payload, runner requirements and network closure |
| A02 | `actions/cache/restore`, `actions/upload-artifact`, `actions/download-artifact` | Tooling + Release; proof, coverage, OSV, release handoff | SHA-pinned clients, GitHub cache/artifact service. Restore/export bytes must pass owning admission; names/keys are selectors, not integrity roots |
| A03 | `actions/upload-pages-artifact`, `actions/deploy-pages` | Docs; Pages upload/deploy | SHA-pinned code, GitHub environment/OIDC. Stage immutable site input separately from public release packages |
| A04 | `googleapis/release-please-action`, `pypa/gh-action-pypi-publish` | Release; release orchestration and OIDC publisher | SHA-pinned code. Review internal container/tool acquisition, producer identity and protected policy; release-please continues to own version/changelog |
| A05 | `SonarSource/sonarqube-scan-action` | Tooling + Security; Sonar job | SHA-pinned action, additional scanner/JRE/service dependencies. Record payload pins or explicit upstream trust exception and credential scope |
| A06 | `step-security/harden-runner`, `ossf/scorecard-action`, `github/codeql-action/upload-sarif` | Security; Scorecard/code scanning | SHA-pinned action code. Harden-runner currently audits egress; Scorecard publishes results with OIDC. Audit transitive tools/images and complete #839's evidence/badge acceptance |
| A07 | [`.github/dependabot.yml`](../../../.github/dependabot.yml), GitHub-managed code scanning and installed status-check apps | Security + Tooling | Weekly GitHub Actions/Python proposals target dev; Z3 excluded deliberately. App-managed engines and databases are external controls, not repo-pinned packages; record owner/config evidence and do not fabricate tool versions |

An action source SHA does not prove the immutability of binaries, containers or
scripts it fetches. The action admission issue must enumerate that transitive
closure at the selected action revision and either pin it, isolate its effect,
or document a reviewed exception. A newly discovered path becomes an inventory
row and blocks qualification; a top-level action pin is not closure evidence.

## Outputs, caches and services

| ID / class | Surface and consumers | Owner | Current boundary / required disposition |
|---|---|---|---|
| O01 managed output | `dist/raes-*.whl`, `dist/raes-*.tar.gz`; local build, corpus integration tests, release smokes | Release | Exact-SHA workflow checks archive membership and installs each. Add digest-bound admission, constrained build/smoke dependencies and producer evidence |
| O02 managed output, currently missing | Release SBOM, build provenance, complete admission bundle | Release + Security | No SBOM generation step exists in `release-please.yml`. Record both runtime distribution dependencies and separate build/tool inventory; attest output subjects and retain evidence |
| O03 managed output | GitHub draft/public Releases and PyPI; `.github/workflows/release-please.yml`, release configs and [`releasing.md`](../../explain/releasing.md) | Release | Release-please, exact-SHA verifier, container gate, separate OIDC PyPI and GitHub jobs exist. Actions handoff retains distributions 7 days; GitHub upload still uses `--clobber`. Add durable admitted bytes, no-overwrite recovery and fresh privileged admission |
| O04 derived delivery output | Sphinx `docs/_build`, Pages artifacts/deployment, Read the Docs build | Docs | Rebuildable public site; source/content gate plus pinned build inputs. Not an upstream package repository. Record source/run for deployment and retain according to site policy |
| C01 derived cache | `uv` package/tool caches, `.venv`, `.nox` | Tooling + Platform | Client-owned performance state, not portable archival format or cross-user trust. Recreate environments; use supported uv cache maintenance. Pre-seeding uses raw admitted wheels/sdists and locks |
| C02 derived cache | `.cache/raes-sdl/tooling` archives/executables, proof installation markers and proof heaps; GitHub Isabelle restore | Tooling + Proof | Several different cache algorithms; path/version or marker hits are weaker than per-use byte verification. Namespace by platform/digest/trust domain; eliminate shared `.download` collisions; protected immutable seed plus private work directories |
| C03 derived evidence until admitted | Coverage XML/JSON, junit, Nox `reports/`, docs link reports, OSV JSON/SARIF, Scorecard SARIF (5-day workflow retention), Sonar upload | Tooling + Security | Ordinary reports are ephemeral. A release admission record must retain its referenced reports with producer, run, SHA and hash; PR reports can never authorize release |
| C04 derived cache / scratch | Container layer stores, test workspaces, cloud/VM disks, temporary source installs, test-generated OCI layouts and module caches | Backend + Platform | Rebuildable per-user/run state. Test OCI input bytes are I11; runtime module bundles remain domain artifacts. No cross-run authority or implicit concurrency guarantee |
| S01 external service and managed freshness data | OSV API/database, vulnerability policies/waivers | Security | Scanner binary pin does not pin vulnerability knowledge. Required online scan errors fail. Disconnected qualification needs an admitted dated database snapshot and expiry policy; absent/stale data means not evaluated, never clean |
| S02 external service | Ground Control governance API, GitHub APIs/status apps, Sonar, Scorecard publishing, documentation link targets, AWS APIs/checkip | Respective governance/Tooling/Security/Backend owner | Not package acquisition. Record availability/credential constraints separately. Offline execution cannot claim live checks; do not replace them with fabricated responses or broaden this issue into an API rewrite |
| D01 domain, excluded | SDL runtime package repositories, software outcomes/acquisition constraints (#1205), typed profiles (#1202/#1208), module registry OCI bundles, backend workload declarations, env-packs/TechVault content | Runtime/SDL/domain owners | Retain existing specs/contracts/admission. Optional shared infrastructure must use distinct namespaces/credentials. Module resolver network code is outside this development-acquisition migration and must not be reused by it |

## Duplication and coverage gaps

The baseline has four generic-binary installers, a common retry helper,
separate Isabelle download/extraction, four vocabulary refresh validators over
five governed source snapshots, live
VM/bootstrap scripts and repeated uv/tool setup in nine workflows. Admission
strength and cache concurrency differ between those paths. Mutable build
dependency resolution, runner images, action-transitive payloads and live
security data sit outside the project lock. Release source identity is stronger
than its durable artifact/evidence retention.

The target consolidates *authority*, native-client policy and local admission
without implementing another network stack. [Migration](migration.md) maps
every row to a responsible issue or an explicit retained/excluded boundary.
