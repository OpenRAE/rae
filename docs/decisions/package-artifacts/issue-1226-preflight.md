# Issue #1226: output-bound SBOM and provenance preflight

## Current scope clarification — #1313

The analysis below is the historical #1226 preflight. Retain useful standard
SBOM/provenance, trusted producer identity, exact output digests and publisher
permission separation. The input inventory now reads the native release and
reusable workflow graph, not a duplicate Actions policy.

#1227 owns ordinary release-byte verification and partial-publication recovery;
#684 owns publication acceptance. Enterprise storage, promotion/revocation
services, mandatory independent copies, disconnected bundles and operational
qualification are cancelled, not dependencies of these release boundaries.
MAINTAINERS.md names the single accountable maintainer. No new human role
separation, deputy or blanket release gate follows from this preflight.

## Historical design — superseded where inconsistent

The remainder records the earlier design. It is not current acceptance policy;
the #1313 ADR amendments and current scope above take precedence.


## Authority and readiness

Architecture review against repository commit `00259d81`. The supplied #1226
issue is the delivery contract under **GOV-913 — Trust And Integrity Of Reusable
Assets**. This note
clarifies [ADR-106](../adrs/adr-106-developer-package-and-artifact-management.md)
and [ADR-107](../adrs/adr-107-artifact-promotion-and-release-admission.md), both
already recorded as accepted through #1229. It neither amends their decisions
nor constitutes implementation, an implementation plan, or release approval.

Before execution, record a named Release/Security implementation owner and
confirm completion of the native blockers #1168, #1216, #1218 and #839 against
the [migration graph](migration.md). Local implementations and accepted ADR
text do not establish current GitHub dependency state. This preflight has not
verified those live relationships or assigned an owner.

The current release workflow constrains builds, rebuilds a wheel from the sdist,
checks corpus membership, and smokes both installed distributions. It has no
output SBOM/provenance generation or durable admission bundle. Do not describe
those target guarantees as already delivered.

[ADR-071](../adrs/adr-071-reusable-asset-trust-and-integrity-policy.md) and the
[GOV-913 spec](../../../specs/supply-chain/reusable-asset-trust-integrity.md)
separate identity, integrity and authenticity. Their reusable-family policy is
declarative, not a release evidence envelope or issuer verifier. #1226 supplies
release evidence under ADR-106/107 without changing that published contract.

## Evidence boundaries

- **Runtime dependencies:** use the exact built wheel's distribution metadata
  and an explicitly selected target/extras closure. A wheel generally declares
  dependencies; their presence in a lock or wheelhouse does not mean their bytes
  are bundled in that wheel. Preserve dependency edges, markers and optional
  scope. Distinguish declared requirements from versions resolved for a tested
  installation. The base installation must remain identifiable independently
  of extras. Here `dev` and `docs` are published optional extras: inventory them
  only in explicitly labeled extra profiles, never as unconditional runtime.
- **Installed observations:** the existing all-extras smoke installs the full
  projected requirements and then installs the candidate with `--no-deps`.
  Dumping that environment cannot establish the candidate's runtime closure.
  Reconcile artifact metadata, locked selection and observed installation;
  missing or inconsistent metadata/edges must fail rather than silently omit
  dependencies. Use maintained metadata/marker parsing and the incumbent locked
  closure walker, not a second dependency resolver or hand-written name parser.
- **Sdist identity:** bind the SBOM to the original `.tar.gz` digest. Keep the
  `from-sdist/` wheel as a separately identified derived test subject, with its
  relationship to the original sdist recorded. Its digest cannot stand in for
  the sdist or the directly built release wheel. Do not assume rebuilding the
  same source yields the same wheel bytes. Preserve source/corpus membership
  evidence alongside dependency evidence.
- **Build/tool/native inputs:** inventory these separately from runtime,
  including generator/verifier dependencies, build backend, Python/uv payloads,
  actions and transitive payloads, actual runner image release/architecture,
  required native inputs and test-image digests. Distinguish selected inputs
  from observed use and external hosted services. A runner label or policy hash
  alone is not an observed host inventory or full host reproducibility claim.
- **Binding:** use standard SBOM and maintained attestation formats, with only
  the minimal internal release association record needed by ADR-107. Bind each
  output basename, size and SHA-256; SBOM and input-inventory digests; repository,
  candidate source SHA, protected producer workflow definition identity, run id
  and attempt, release id/tag; target/extras profile; lock/export/policy hashes;
  and corpus/smoke/test results. Candidate source and producer workflow revisions
  are separate identities. Every evidence association must lead to the exact
  wheel/sdist subjects; neither filenames nor matching versions establish it.
  Authenticate sidecar associations as well as subjects, without circular
  self-hashing or a second independently maintained subject list.

## Cross-cutting layers and canonical incumbents

All paths below are repository-relative. Extend the existing authority or
boundary where needed; an inventory record never grants execution authority.

| Layer | Incumbent and required behavior |
|---|---|
| Dependency selection | `implementations/python/{pyproject.toml,uv.lock}`, `implementations/tooling/python/{pyproject.toml,uv.lock,build-constraints.txt,smoke/}`; `tools/generate_python_closures.py` and `tools/generate_python_closures_locks.py`. Admit generator/verifier dependencies in the tool lock, including transitive/build needs, and regenerate hash-complete projections. Keep frozen consumers. A native generator instead enters the existing artifact/host policy; a SHA-pinned action still needs payload admission. |
| Profiles and environment shapes | `tools/python_closure_profiles.py` owns `PythonClosureProfile`, runtime checks, the closed tool command allowlist and `closure_environment`; `implementations/tooling/profiles/development-profiles.json` and its schema own context/target/extras. Select reviewed profile ids, not arbitrary package lists, CLI fragments or environment overlays. Preserve minimal child environments, disabled keyring/interpreter downloads, explicit index policy, mirror-only isolation and verified offline wheelhouses. Do not broaden candidate environments to pass signing/storage credentials. |
| Static policy and schemas | `tools/check_tooling_artifact_policy.py`, `tools/tooling_artifact_policy_common.py`, `tools/tooling_policy_gate.py`, and `implementations/tooling/schemas/` own bounded JSON, local schema references, closed shapes, path/platform checks, forbidden executable keys, credential-bearing locator checks and cross-record joins. Update canonical schema, records and semantic checks together. New acquisition sites also affect `selector-bindings.json` and `inventory-coverage.json`; dynamic subprocess commands need their existing disposition. |
| Producer trust and authorization | `implementations/tooling/admission-policy.json` is the policy authority; its current closed v1 schema has no release producer/issuer fields. Extend that authority deliberately with Security review; a string in `accepted_evidence` does not validate an issuer. Pin the accepted issuer, repository, protected workflow identity and subject expectations in trusted policy. Candidate lock/policy bytes can be recorded as inputs but cannot select the publisher's acceptance policy. |
| Workflow security | `.github/workflows/release-please.yml`, `canonical-verification.yml`, `implementations/tooling/actions-policy.json` and `action_policy_*.py` own event/ref trust, reusable-workflow propagation, permissions, credentials, runner joins, action inputs and cache/artifact roles. Use their safe YAML parser and closed condition grammar. Preserve `persist-credentials: false`. New action sources/use sites, hosted-service exceptions and OIDC/attestation effects require complete admission records. `test_release_workflows.py::_REVIEWED_JOB_WRITE_SCOPES` separately enforces exact privileged-job grants; do not relax it globally. |
| Host/process/filesystem | `tools/bootstrap_profile.py` binds host qualification; `tools/python_closure.py` builds and smokes outside checkout; `tools/python_closure_wheelhouse.py` owns path admission, regular-file hashing and exact inventory checks. Use private job storage, bounded reads/processes, fixed argument arrays, validated basenames and explicit output membership. Reject links, traversal, duplicate/extra/missing subjects and unsupported formats before trust. Existing path/hash helpers do not provide an atomic hostile-writer snapshot: keep candidate writers out of signing/storage jobs and rehash each transferred copy. |
| Diagnostics and validation failures | Reuse `tools.policy.common.PolicyFailure` and the existing text/JSON policy envelope; keep the closure tooling's `ValueError`/`RuntimeError` and bounded client failure boundary. Do not introduce application HTTP errors or a parallel exception hierarchy. Public failures carry stable classes and logical ids; suppress raw tool stderr, tracebacks containing client output, response bodies, signed URLs and private inventory details. Record safe subject/run/profile/policy identities and verification/retention outcomes for audit. |
| Policy identity and persistence | Reuse `tools/check_tooling_artifact_policy.py::tooling_policy_sha256`; it deliberately excludes qualification results and hashes defined authority sets. Register any new authority in its coverage and retain separately named raw lock/export/workflow hashes; do not relabel the aggregate as a raw-file hash. Use ADR-107's retained bundle and same-byte/readback rules, not a writable cache or research evidence index as release authority. |
| Verification and governance | Nox (`noxfile.py`, `tools/nox_support/`) remains the verification graph. Preserve `test_release_workflows.py`, `test_corpus_packaging.py` and the Python-closure/action-admission cases in `test_tooling_artifact_policy.py`. Keep `.ground-control.yaml`, `.gc/plan-rules.md`, repository policy, requirement governance, ADR pins and pre-commit checks visible. Use `RAES_REQUIREMENT_UID=GOV-913` when the branch lacks the UID; preserve traceability without treating historical links as proof of this issue's completion. |

The complete action-policy chain is `action_policy_yaml.py` (duplicate/alias-free
parsing), `action_policy_conditions.py` (event/ref, condition and secret shapes),
`action_policy_matrix.py` (runner joins), `action_policy_sources.py` and
`action_policy_effects.py` (source/transitive capabilities), then
`action_policy_jobs.py`, `action_policy_job_steps.py` and `action_policy_main.py`
(job/use-site and reusable-workflow grants). Schema acceptance of `attestations`
or `id-token` permissions alone does not authorize a new signing boundary.
The static action checks do not prove arbitrary shell code safe: bind untrusted
values through explicit, validated environment fields and fixed argv, never
interpolate candidate metadata into shell source or workflow output commands.

Evidence is untrusted parser input even after transfer: bound file size, nesting,
archive expansion/member counts and verifier output; reject duplicate keys,
ambiguous subjects and unsupported format versions. Use maintained SBOM/metadata
parsers without importing the candidate package, executing build hooks or
fetching candidate-supplied schema references. `load_bounded_json_object` is the
incumbent repository-JSON boundary, not a complete hostile-stream validator;
likewise `python_closure._run` limits time but buffers captured output. Extend
the appropriate local boundary where needed, preserving safe failure envelopes.

Signing must run at a protected producer boundary that never imports or executes
candidate scripts, build hooks, policy or installed packages. A build job must
not gain OIDC or publication permissions merely to attach an attestation. The
signer must verify the trusted workflow/run handoff and measure received bytes;
signing arbitrary candidate JSON would only authenticate an unchecked claim.
Keep storage-write, attestation and PyPI/GitHub publication identities separate.
External rulesets, protected environments, publisher registration and storage
ACLs must prevent signing credentials from authorizing package publication.
Tokens belong in the maintained client's supported protected credential channel,
never argv, URLs, workflow outputs, persisted Git configuration or evidence.
No untrusted job may populate a cache later executed by a privileged job.
Protected tools, import paths, working directory, executable search path and
home/config must come from the trusted producer environment. A protected script
launched inside a candidate checkout can still import or execute candidate code.

Use the maintained verifier for signatures, certificate/issuer checks and its
required trust material; use repository validation for release association and
policy decisions. Do not implement cryptography, certificate verification or
HTTP acquisition. A successful signature with the wrong repository/workflow,
run/attempt, source, predicate or subject is a rejection. Skips, missing evidence,
malformed verifier output, cancellations and infrastructure failures never
become admission. Expected identities come from trusted context, not the bundle
being verified. Current status/verification-time rules remain those in
[operations](operations.md).

## Retention, extension seam and acceptance limits

Keep distribution files and evidence in explicit separate directories/roles.
The current corpus check rejects unexpected distribution files, and publishers
consume the distribution directory: adding SBOM JSON to that directory must not
broaden upload globs or bypass the exact wheel/sdist set. Preserve both installed
smokes, zero-skip required Docker testing and exact-SHA checks, including
post-approval release/tag/SHA revalidation.
The current GitHub attachment step still uses `--clobber`; that is an incumbent
gap assigned to #1227, not a publication pattern to copy for retained evidence.
Absent or rejected evidence must block the handoff; #1226 cannot satisfy T19
with an optional report while the publisher remains reachable on failure.

#1226 must demonstrate retention outside short-lived Actions artifacts; uploading
to Actions or an attestation service alone is not that demonstration. Retain
original wheel/sdist, associated SBOM/input inventory, attestation verification
material and lock/policy snapshots under the existing storage-interface design,
with readback digests, a durable locator and a named retention owner. Apply the
supported-release-lifetime-plus-one-year rule and restricted/public separation
from operations.md. Record actual retention evidence; do not claim independent
copies or disaster recovery without qualification. #1227 owns full publisher
admission and same-byte recovery, #1224 the storage service, and #1228 operations
qualification. If the retention destination is unavailable, record the unmet
acceptance criterion and coordinate the native graph; do not waive #1226's AC.

The extension seam is a reviewed **target/extras profile plus standard evidence
format/version and producer-policy identity**. Reuse the closure walker with
explicit root extras/groups; its current all-or-none root-optional switch is
not a named-extras selector. A second target or extra should extend profile
data and qualification, not copy a workflow, package list or resolver. Keep
marker evaluation bound to the selected target: `target_environment()` currently
inherits some host marker fields and synthesizes `python_full_version` as
`major.minor.0`. Patch-sensitive or cross-OS resolution must use the reviewed
target's full marker environment rather than silently inheriting the generator
host. Test those distinctions in the incumbent closure walker.

Keep storage locator/profile selection independent of output identity. Choose and
admit the maintained generator/verifier and supported formats before execution;
do not add an open plugin framework or arbitrary predicate/command fields.

Implementation evidence must execute [T03, T04 and T19](operations.md): declared
CPython 3.11–3.14/ABI/extras qualification; hostile candidate/credential isolation;
and missing/extra/replaced wheel, sdist or SBOM, absent attestation, foreign
producer and wrong subject rejection. Include substituted input inventories,
run/attempt replay, sidecar swaps, generator/verifier failures and safe diagnostic
checks at the actual handoff. Static YAML assertions alone cannot establish
credential isolation or cryptographic verification. Record exact tool/platform/
policy identities and retained evidence. This documentation change executes none
of those release acceptance tests and does not claim implementation readiness.

Non-goals: runtime SDL/OCI/module resolution, published `contracts/schemas/`,
application controllers/DTOs/services/repositories, research/run provenance,
new generic evidence storage, a custom downloader or retry engine, release-please
version/changelog changes, full #1227 recovery, or bit-for-bit reproducibility.
The similarly named `raes_contracts` provenance models and
`tools/evidence_bundle_index.py` have domain/research authority and must not be
repurposed as release schemas. Do not treat an SBOM as a vulnerability verdict,
an attestation as code safety, or a lock digest as evidence of actual execution.
