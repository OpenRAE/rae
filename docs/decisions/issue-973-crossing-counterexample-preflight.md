# Issue 973: Participant-Crossing Counterexample Preflight

Date: 2026-10-29. Requirements: SEM-232, ASR-535, SEM-230, GOV-913.
Scope: deterministic offline mutation and safe negative evidence for #973.

[ADR-100](adrs/adr-100-participant-crossing-bisimulation.md) already owns the
architecture. No new ADR, relation, runtime service, or public contract is
needed. This note closes the mutation, checker, and publication boundaries;
it is neither an implementation plan nor evidence that a check has run.

## Exact inputs and ownership

Use `participant-crossing-dpbb-finite-v1@rev2`, both model revisions `rev2`,
`participant-crossing-projection@rev1`, and catalog `rev8`. Resolve the pinned
catalog through `load_behavioral_relation_catalog_revision()`, not the current
catalog. The [executable rules](../../specs/formal/participant-semantics/participant-crossing-models.md)
supersede the historical rev1 sketch. The separate #1395 multi-operation
profile does not expand this issue's carrier.

The semantic owner is `implementations/formal/participant_crossing/`.
`abstract.py` and `concrete.py` independently construct the baselines;
`graph.py`, `aut.py`, `ingress.py`, and `export.py` supply inert plumbing.
Mutations operate on copies of validated baseline graphs or exported bytes.
Never change their transition authorities, profile, or canonical projection
to admit a deliberately faulty specimen. Share serialization and validation,
not a transition oracle or an expected-answer oracle.

The [#972 mapping](../../specs/formal/participant-semantics/participant-crossing-runtime-mapping.md)
is a separately pinned dependency with matches, incompatibilities and gaps.
Its existence is not complete runtime realization. Preserve its classifications
and source identity; a historical capture cannot become current by changing
its pins. Formal mutation checks need no live API, backend, or store execution.

## GOV-913: integrity, authenticity and review authority

[ADR-071](adrs/adr-071-reusable-asset-trust-and-integrity-policy.md) and the
[reusable-asset trust specification](../../specs/supply-chain/reusable-asset-trust-integrity.md)
own these meanings. The corpus plays the existing `evidence_artifact` role;
it does not create another asset family, registry or universal trusted-asset
object. Its internal manifest binds formal evidence, not ecosystem trust policy.
`ReusableAssetTrustPolicyModel` in `raes_contracts/contracts/reusable_assets.py`
and the published `reusable-asset-trust-policy-v1` schema validate any consumed
policy declaration. They require complete family coverage, unique evidence
classes, required integrity and threshold-backed signature expectations.
A corpus-only family fragment is not a valid replacement policy.

The reference policy requires evidence checksums and recommends authenticity
signatures. It is a conformance fixture, not an installed signer authority.
Policy shape validation neither verifies payload bytes nor authenticates a
producer. Pin any applied policy by exact content identity; select it from
reviewed configuration, never from the candidate's own proposed trust rules.
Keep an absent signature explicit. If a consumer requires authenticity, absent
or unverifiable signatures block that use; do not silently downgrade the
requirement or claim that this unsigned corpus satisfies it.

Keep the following evidence distinct:

- A case id names the case. Recomputed byte digests bind the concrete AUT,
  sidecar, witness and manifest files. A manifest and payload replaced together
  can be self-consistent; compare the manifest against an independently retained,
  reviewed repository pin before accepting the bundle.
- Source and tool pins record derivation. They do not establish who approved
  the mutation, whether its expected result is correct, or whether historical
  mapping observations describe the current runtime.
- Independent review must refer to the exact mutation and expectation digest
  through the existing review workflow. A producer-authored `reviewed: true`
  field or reviewer name is not review evidence. Changed inputs, deltas or
  expectations need corresponding review; preserve earlier records.
- Cryptographic authenticity requires verified signatures over the exact
  subject and an independently selected signer policy. Module-registry
  `signing.py` verifies module-specific subjects; release evidence uses
  `tools/release_evidence_verifier.py` and `release_evidence_admission.py` for
  release-specific subjects and producers. Neither is a generic corpus signer.
  Do not copy their cryptography, claim their approvals, or introduce signing
  credentials/services for #973. A later signed distribution needs an explicit
  subject/policy binding at its existing publication boundary.

`ExperimentChecksumModel` already defines portable checksum metadata when
evidence enters experiment records; it checks shape and digest length, not
content. Internal corpus files retain `export.digest()` byte identity and
`raes_contracts.canonical` semantic JSON identity. Name these separately:
canonicalizing parsed JSON cannot verify a raw-file checksum, and a trailing
newline changes the latter. Keep review/signature references outside the subject
they attest to, avoiding self-referential digests and machine-specific metadata.

## Negative evidence must mean the selected relation failed

Each case binds its baseline side, exact before/after graph digests, initial
states, mutation revision, semantic location, explicit edge delta, and reviewed
expectation. Select locations using the pinned synthetic state map and label,
not an unexplained ordinal. Verify applicability, nonzero change, reachability
from the initial state, and absence of unintended edits. Preserve the original
five hidden label classes in review data, even though AUT uses `internal`.

Baseline closure checks in `export._validate_graph()` remain mandatory for
baseline construction. A fault specimen intentionally violates that transition
authority; do not disable its checks or demand that a mutant satisfy them.
Mutants still need bounded structural validation, exact counts and endpoints,
and independent validation of their declared delta. Record reachable counts
separately if edge removal strands states. Any renumbering needs a bound map;
neither truncation nor minimization may erase the behavior under examination.

The existing [worked cases](../research/participant-bisimulation/worked-evidence.md)
are obligations, not observed results. Their minimum meaning is:

| Failure shape | Required distinction |
| --- | --- |
| Hidden denial | Relabel a reachable `crossing.decision.deny` only in the faulty specimen. Keep the baseline projection fixed. |
| Hidden divergence | Add a reachable internal cycle after a finite visible prefix. Check divergence, not merely a changed edge count or a visible retry cycle. |
| Removed delivery | Remove an enabled delivery branch after permitted transformation. Show the affected reachable choice; deleting an unreachable edge proves nothing. |
| Later-cut replay admitted | Start with a retained p0 result, visibly advance to p1, and incorrectly admit replay. Keep request identity and retained input fixed; do not substitute a fresh request or equate policy cut with history head. |
| Redacted occurrence, error, deadlock, completion | Observation remains visible without payload. Missing outgoing transitions are structural deadlock. Rev2 `terminal` completes one crossing and can still enable retry/cut advance; AUT has no success predicate. Sanitized runtime errors outside the closed alphabet remain unsupported/incompatible or separately scoped calibration cases, never a new hidden label. |
| Unsafe counterexample | Reject payload, host/process information, unknown syntax, and oversized output before publication. This is an evidence-validation failure, not a negative bisimulation result. |

Record strong, weak, branching, and divergence-preserving branching results
separately, with the exact comparison mode and hiding operation. Calibration
pairs must distinguish finite internal stuttering, weak versus branching
choice, and ordinary branching versus divergence preservation. Keep those
pairs explicitly separate from the governed crossing carrier. A trace witness
can explain a failure; it cannot stand in for the selected DPBB decision.
Expected outcomes are reviewed assertions, not measurements. Every required
failure shape needs independent review tied to its exact mutation digest.

Bind each result to its ordered input pair and identify the mutated side.
A reachable edge change can still preserve the selected relation. Include
unchanged-input controls and verify that reversing the declared delta restores
the original bytes; relation-separation calibration pairs must exercise the
same adapter and hiding settings. These controls detect an always-negative
adapter without establishing the pending abstract/concrete theorem. An
unrelated mismatch in that pair cannot establish that a mutation is effective;
use an isolated baseline-versus-mutant comparison or independently checked
evidence locating the violated relation obligation.

The tool outcome has at least three distinct meanings: equivalent,
not-equivalent, and no valid decision. Invalid input, unsupported mode, missing
tool, timeout, resource exhaustion, malformed output, and process failure
belong to the last category and block a completed corpus. Pin and test the
tool's actual result protocol; neither exit success nor exit failure alone is
the relation verdict. Keep operational status separate from semantic result.

[mCRL2 202607.0 documents](https://www.mcrl2.org/web/user_manual/tools/release/ltscompare.html)
tested diagnostic formulas for `bisim`, `branching-bisim`, and `trace`, not
`dpbranching-bisim`. Its hiding option also preserves native internal actions
already present in the input. Continue rejecting undeclared tau encodings;
do not broaden the profile or substitute another mode to obtain a formula.
For a supported Hennessy-Milner witness, admit a bounded syntax and label set,
check its truth in the first input and falsity in the second after the exact
hiding operation, then render safe canonical bytes. Truncation or arbitrary
text replacement can change meaning and is not sanitization. An unsupported
or over-budget witness cannot be represented as a checked formula.
A formula for a stronger relation can distinguish DPBB-equivalent systems.
Label auxiliary formulas with their actual mode; truth checking alone does
not make them DPBB counterexamples. Require a justification valid for DPBB.

For pure divergence, an independent negative checker must consume the exact
graph bytes and verify a reachable nonempty tau cycle and the opposing
divergence obligation. In this rev2 profile the abstract model has no tau
edges: independently check that fact across its complete graph, and check the
concrete prefix and cycle. This supports the narrow divergence refutation
without a general second bisimulation engine. A cycle somewhere in an arbitrary
graph pair is insufficient; future profiles with abstract divergence require
relation-sensitive reasoning. The independent checker must not trust the
mutation id, producer verdict, supplied reachability, or a rank assertion.

## Cross-cutting boundaries to reuse

Python module paths below are under `implementations/python/packages/` unless
otherwise qualified. These are requirements for implementation, not assertions
that this documentation change delivers the controls.

| Layer | Canonical owner and required treatment |
| --- | --- |
| Filesystem ingress | Reuse formal `ingress.safe_path()` / `read_bytes()` and `tools.policy.common.safe_repo_path()`. Enforce repo-relative paths, no symlink traversal, regular files, byte bounds and no-follow descriptor reads. Read back tool-created outputs through this boundary too; a portable reference string alone does not authorize a path. |
| JSON, AUT and profile validation | Reuse `json_ingress.parse_bounded_json_object()` with depth/byte limits, `aut.parse_aut()` / `render_aut()`, `BehavioralRelationProfileModel`, `_participant_crossing_profile.py`, and exact-revision loaders. Reject duplicate JSON keys/edges, unknown fields/labels, nonfinite numbers, bad endpoints/counts and native tau. Use strict bounded integers, excluding booleans/coerced strings. The corpus adds only its own closed metadata/delta/witness checks, not copies of profile or AUT schemas. |
| Claim and schema joins | Reuse `behavioral_relations.validate_behavioral_claim_binding()` when consuming a claim binding, including both carriers and exact projection/catalog revisions. A mutation's profile reference identifies the baseline; it must not falsely assert that the faulty graph conforms to the profile. Do not reuse opacity-specific evidence DTOs. An internal closed corpus manifest suffices; any later public schema change must follow ADR-009, `contracts/schema-publication-manifest.json`, its entries, generator parity and fixtures. |
| Authentication and policy | This offline synthetic corpus traverses no HTTP or principal-authentication gate. It grants no runtime authority. Any separately exercised live case retains `RuntimeControlPlane`, `raes_runtime/control_plane_api/_auth.py`, `ControlPlaneSecurityConfig.strict_defaults()`, `raes_runtime/participant_crossing_policy.py`, exact-cut and API-407 support admission. Never bypass those gates to make a counterexample fit. |
| Runtime DTOs and persistence | API-423 `ParticipantCrossingOccurrenceModel` and `validate_participant_crossing_occurrence_context()`, `participant_crossing_history.py`, and `ControlPlaneStore.commit_participant_transition()` already own typed context, predecessor/history joins and atomic persistence. Reference their existing mapping evidence. Add no proof fields, mutation toggles, replacement store, runtime observer or backend changes. |
| Tool configuration and acquisition | `implementations/tooling/artifacts.lock.json`, `profiles/development-profiles.json`, `admission-policy.json`, host profiles and their schemas own admission. Use `tools.tooling_policy_gate.load_tooling_artifact_selection()`, `tooling_artifact_selection.py`, `maintained_client_acquisition.py`, and `verified_tree_installation.py`; these bind platform, dependencies, raw checksum and installed tree. An OCI choice instead uses the existing OCI selection/policy path. No parallel downloader, cache, mutable tag, PATH-selected binary or fabricated checksum. |
| Host/process isolation | `tools/isabelle_tool.py` and `isabelle_sandbox.py` are the incumbent proof-process controls: fixed argv without a shell, verified installation, restricted mounts, private state, cleared environment, network isolation, bounded time/CPU/address space/files/output and disabled core dumps. Reuse those controls through a narrow tool adapter; their Isabelle-specific command/session settings are not a ready-made mCRL2 runner. Bound output while it is produced, terminate child processes on timeout, and reject unsupported sandbox hosts rather than silently falling back. |
| Secrets and environment shapes | No credentials, secret resolution, live payloads, policy bodies or environment-selected semantics are needed. Never inspect secret files or export/hash ambient environment values. Keep subprocess env explicit and minimal; argv/filenames contain only fixed options and safe synthetic input references. If future runtime fixtures need env bindings, retain `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py`, `runtime_values.py`, and `raes_contracts/secret_references.py` sensitivity, provenance, unique-name and literal/`value_from` checks. No new env syntax. |
| Errors and observability | Preserve existing `ValueError` / `StrictJsonIngressError` admission and bounded tool-adapter failures; do not create a parallel exception hierarchy. The formal `__main__.py` fixed-message boundary is the CLI precedent. Emit only allowlisted case ids, stages, counts, digests and result classes; never forward exception strings, validation input dumps, argv, stderr, formulas or tracebacks into logs. Existing conformance consumers retain `raes_conformance/conformance/diagnostics.py:sanitized_failure_message()`; formal tooling needs no new dependency on conformance. `raes_runtime/control_plane_api/_operation_routes.py` retains authentication before redacted 422 responses and the fixed HTTP 500 envelope. `tools/nox_support/runner.py:SessionReporter` owns workflow reporting; `PolicyFailure` owns policy failures. Runtime diagnostic shape validation is not a sanitizer. |
| Identity and publication | Reuse `raes_contracts.canonical` for RFC 8785 JSON identity and `export.digest()` for exact file bytes. Bind baseline/mutant AUT, semantic sidecars, mutation source, profile/projection/catalog, mapping capture, checker/independent-checker sources, tool version/provenance, command, bounds, counts, reviewed expectation, observed result and safe witness. Keep the digest graph acyclic. Reuse `export.publish_bundle()` / `_check_expected()` for complete staged publication and refusal to overwrite drift; its documented assumption is a trusted parent and exclusive writer, not a hostile shared filesystem. |

No mCRL2 artifact is currently admitted in the repository lock, and there is
no existing mCRL2 execution wrapper. This is a prerequisite for a recorded
mCRL2 result, not permission to bootstrap one outside the tooling policy.
The #973 negative checks and #974 positive check need one shared admitted tool
boundary. Do not make #973 depend on #974's completed positive result, or
publish expected results as measured while tool admission is outstanding.

Tooling lock/profile schemas are closed, and
`tooling_artifact_policy_common.FORBIDDEN_EXECUTABLE_KEYS` rejects command,
argv, script and hook fields. Keep command construction in the fixed wrapper;
record its safe command identity in evidence, not executable policy metadata.
Bounded resource settings belong to the reviewed wrapper or its explicitly
validated options, not arbitrary additions to the lock/profile schemas.
Host prerequisites must cover the admitted tool's actual native libraries,
locale and sandbox, rather than copying Isabelle's fonts/JVM assumptions.
Tool provenance review also covers license and redistribution conditions;
verification never acquires tools implicitly.

Admission must join the selected artifact, locator, development profile and
host profile through `tooling_artifact_policy_artifacts.py` and
`selector-bindings.json`; `tool_versions.py` is a checked projection, not a
second version authority. The existing `proof-linux-x86_64` profile admits
Isabelle/uv, and its Ubuntu 22.04 host does not establish mCRL2 library
compatibility. Its `proof_support` policy also requires Isabelle's font
prerequisites. Preserve those checks; express the new tool's actual needs
through the existing host-profile mechanism, without weakening another tool's
closure or claiming that architecture alone establishes host compatibility.
`validated_descriptor()` requires exactly one selected executable: select
`ltscompare`, while the installed-tree identity still covers all package files.

Archive format is also checked outside the extractor: today the lock schema,
`tools/tooling_installed_tree.py`, `verified_tree_validation.py`, and
`verified_tree_manifest.py` all require `tar.gz`. If tool admission selects a
Debian package, extend that format join through the existing archive admission
and installation transaction. Preserve existing tar.gz bytes and identities.
A maintained package reader may decode already verified raw bytes without
installing packages or running maintainer scripts; it needs an admitted host
prerequisite, fixed argv, minimal environment, bounded decompression/output and
process cleanup too. Keep the raw archive and complete tree identities bound
together. Do not bypass the join with an unpinned repack, replace the global
default format, or implement a separate installer. Make format selection an
explicit closed parameter shared by descriptor and manifest validation.
The decoder must consume the bytes held by `opened_verified_raw()`, not reopen
an untrusted pathname after its digest check. Preserve ownership, no-follow,
inode and post-read stability checks. Confined relative symlinks are supported
by the incumbent tree validator; reject unsafe links, hard links and special
files without replacing that policy with a second extractor's defaults.

`export.publish_bundle()` trusts its supplied bundle keys. Before calling it,
validate the exact artifact inventory, single-component allowlisted filenames,
per-file and total byte bounds, and all cross-file digests. A safe output root
does not make an untrusted filename safe. Re-read and validate tool outputs
before publication. Canonical corpus identity excludes elapsed times, temporary
paths and other host-specific measurements; optional workflow telemetry stays
outside the reproducible counterexample bytes. An invalid or partial run must
not publish a completed-corpus record.
The current publisher fsyncs files but does not fsync the publication's parent
directory. Atomic visibility is not a crash-durability guarantee. Keep its
trusted-parent, exclusive-writer scope explicit; if durable publication or
concurrent writers become necessary, extend the existing publication boundary
using the installer transaction precedents instead of claiming those properties
from rename alone.

## Evidence lifetime, extension seam and verification boundary

Retained `crossing-models/rev2` bytes remain immutable. Current exporter source
pins can legitimately differ from its historical manifest while model bytes
remain unchanged; `test_issue_971_crossing_export.py` and
`runtime_mapping_export.py` already distinguish these cases. Verify retained
artifact digests, reproduce consumed model bytes, and report source drift
explicitly. Do not rewrite old manifests or simply refresh their hashes.
The mapping source inventory also includes formal code, tools, contracts and
tests: new corpus code can change its capture identity without changing the
runtime. Keep the mapping explicitly historical or collect new observations
for a current-source claim; never relabel old observations.

Use immutable content-addressed corpus captures whose identity includes the
mutations and consumed inputs, not a globally allocated next revision or only
the baseline source hash. Preserve a pinned inventory so a missing required
case cannot disappear silently. For formal/specification research records,
reuse `python -m tools.research_capture record` and
[research capture rules](../develop/research-captures.md); that recorder
currently supports those two research families, not an arbitrary new corpus
family. The formal corpus can use the existing bundle publisher and be pinned
from those records. Preserve retention receipts and historical baselines;
numbered research publication remains a clean `dev` integration action.

The extension seam is explicit case data binding an admitted profile revision,
model/projection identities, mutation kind/revision, checked location/delta,
expected per-relation results and bounded witness capability. Keep tool
selection in tooling configuration and resource bounds in the reviewed adapter,
not the semantic profile. A later #1395 corpus can select its own labels,
counts and budgets through existing
codec parameters and a separate admitted profile binding. Do not loosen rev2,
derive labels from untrusted tool output, auto-select the latest profile, or
build a generic plugin framework for this extension.

Reuse the #971 profile/model/export tests, #972 mapping/ownership tests, #1395
parameterized codec precedents, and tooling admission tests. New regression
evidence must distinguish an ineffective mutation, unchecked expectation,
unsupported formula, false cycle witness, malformed/tool-failure output,
source/artifact drift, unsafe output and interrupted publication. Independent
replay recomputes bytes and witness checks in a clean environment; it cannot
reuse the producer's verdict as its oracle.
Mocks can exercise wrapper failures, but cannot supply published relation results.
Trust-boundary regressions must also reject a jointly replaced manifest and
payload against the retained pin, stale mutation review, policy substitution,
and confusion between raw-file and canonical JSON digests. Preserve unsigned
status without treating it as either authenticated evidence or a relation failure.

`.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`,
`tools/policy/requirement_order.yaml`, requirement scopes, `.pre-commit-config.yaml`,
`noxfile.py` / `tools/nox_support`, and `.github/workflows/canonical-verification.yml`
remain the workflow owners. Keep `RAES_REQUIREMENT_UID=SEM-232` explicit when
needed, preserve formal/runtime ownership and traceability, and use targeted
tests or `verify-fast-feedback` locally. Full verification and integration
suites remain in CI; add no duplicate workflow or acquisition in test setup.
An issue reference or `RAES_REQUIREMENT_UID` alone does not admit tooling
changes: `requirement_scope.py` binds exact files to existing requirement
predicates. Check the eventual tooling and guidance paths against those owners;
use the existing issue-scope mechanism when multiple owners are needed. Do not
broaden the formal phase to own arbitrary runtime or tooling code.

## Non-goals

This corpus establishes no positive equivalence, proof certificate, complete
runtime realization, backend conformance, policy noninterference or predicate
opacity. It must not advance assurance fulfillment or scientific-completeness
claims. #974 owns the positive finite model-check decision, #975 independent
reproduction, and #976 the resulting public claims. No change to runtime retry,
authorization, error, delivery, policy or persistence behavior belongs here.
No result extends beyond the named participant/audience, carrier, total order,
untimed/nonprobabilistic/sequential execution, fixed controller, policy cuts
or backend-independent boundary.
