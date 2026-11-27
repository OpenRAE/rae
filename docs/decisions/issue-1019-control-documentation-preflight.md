# Revised control documentation: architecture preflight

Issue #1019 is the contract for this requirement-free documentation change.
Inspection baseline: `28638c1d`. This note sets boundaries; it is not an
implementation plan, normative specification, or completion evidence.

## Decision and authority

Reconcile the existing reference, migration, and public guidance with the
implemented paths and their bounded evidence. No new ADR, schema, vocabulary,
runtime abstraction, or publication system is needed. ADR-009/061 own artifact
authority and schema evolution; ADR-059 protects accepted ADR interpretation.
ADR-095/102/104/108/110/111/113 own delivery, mixed composition, runtime,
modular control, reusable policy, applicability, and execution machinery.
[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) assigns native
effects, credentials, lifecycle, and qualification to backend distributions.

Normative meaning comes from `specs/` and `contracts/`, including the
participant-control concept authority and formal participant-semantics specs.
Implementation and execution evidence establish which paths currently work;
they cannot silently amend that meaning. Guidance must name a mismatch or
unsupported path instead of changing either authority to make an example pass.

The supplied diagnosis URL is a historical reference; its path is absent from
this checkout. The current prerequisite authorities are the
[#1018 demonstration](../explain/reference/mixed-control-demonstration.md) and
[#1374 observed-evidence design](issue-1374-observed-opacity-evidence-design.md).
The former tests RAE with controlled providers on a `hermetic-live` basis. It
does not qualify native backends or complete the broader ASR-537 protocol.
The latter establishes observed runtime mediation for its pinned opacity
profile, not backend-native ownership or backend-conformance claims.

## Terms and outcomes that must stay separate

| Distinction | Required interpretation |
| --- | --- |
| Policy / occurrence | A reusable policy permits applications; an occurrence records one actual attempt at an exact cut. A cycle needs fresh identities and evidence. Exact retry retrieves the retained receipt; it is not another cycle. Finite-script conversion does not authorize reusable traces. |
| Admitted apparatus / applicable slots | The selection retains the complete apparatus. Profile-owned coverage and trusted context determine applicability at a cut. Missing results, empty coverage, and provider `None` do not prove inapplicability. |
| Required / optional results | Required dependency closure includes advisory inputs needed by a mandatory consumer. Advice content has no direct veto, but required input availability is mandatory. Invalid optional output becomes value-independent lost advice at the existing boundary. |
| Parent decision / effects | Permit, deny, and withhold decide the parent. Evaluation eligibility is not dispatch permission. Consequences after denial require independent authority, exact prerequisites, and successful mandatory composition. |
| Request / admission / execution / delivery / observation | Parsing accepts shape; authorization and admission govern action; committed owner evidence establishes effects. An accepted receipt may identify a failed or indeterminate operation. Delivery needs its own boundary evidence; observation needs its own record. Missing evidence proves neither success nor denial. |
| World inject / participant disclosure | A participant-free world effect uses orchestration identities and its own operation/outcome. A separate governed delivery joins that result to a recipient, audience, episode, and policy cut. Never create a fictitious participant to trigger the world effect. |
| Controller / provider / observer | Multiple execution providers do not imply multiple acting controllers. Administrative history is not participant-visible history. A provider acknowledgement is not proof of cessation or an independent observation. |
| Authored recovery / transport recovery | Retry, resume, compensation, and fresh-trial intent require their owning admission and evidence. Restart, idempotency, timeout, or an absent-effect report alone cannot authorize another effect or prove cessation. |

API-409 occurrence v2 and API-424 evaluation v2 are independent lineages.
Keep semantic revision, wire contract ID, schema hash, profile revision,
provider protocol, implementation identity, and store reader version distinct.
Do not present these as one global "control v2" switch.

## Repository surfaces and existing evidence owners

| Concern | Canonical incumbents and documentation boundary |
| --- | --- |
| Repeated control | `docs/explain/reference/reusable-participant-control.md`, `docs/migration/reusable-mixed-control.md`, and `docs/migration/mixed-control-finite-script-conversion.md`; `MixedControlRuntimeBinding`, API-409 occurrence/context validation and history fold; `test_issue_1364_control_history.py` and the reusable case in `mixed_control_demonstration.py`. |
| Applicability and effects | `modular-participant-control-contracts.md`, `modular-control-conformance.md`, `docs/migration/control-applicability-and-evaluation.md`; `raes_contracts/contracts/participant_control_*_v2.py`, especially `derive_control_composition_v2`, and the existing runtime evaluation/effect owners. V1 interpretation remains independently supported. |
| Participant-free injects | `specs/sdl/external-injects.md`, `docs/explain/reference/inject-occurrence-contracts.md`, `docs/public/guides/external-injects.md`, and `docs/explain/sdl/external-inject-compatibility.md`; `InjectExecutionResolver`, `submit_inject`, occurrence/outcome/correlation validators, `inject_execution_fixtures.py`, and `test_issue_1367_inject_execution.py`. |
| Failure and recovery choices | `specs/sdl/execution-recovery.md`, `execution-recovery-migration.md`, `backend-operation-supervision.md`, and `docs/explain/sdl/control-plane-operations.md`; `ExecutionPolicyCapabilities`, compiler/planner execution-policy helpers, `require_backend_execution_policy_admission`, and `test_issue_1361_execution_policy.py`. |
| Mixed arrangements | The #1018 reference, design, retained `docs/examples/mixed-control-demonstration/record.json`, collector, and `test_issue_1018_mixed_control_demonstration.py`; the existing mixed and modular conformance runners and `BackendConformanceReport`. Do not add a documentation-specific runner or success definition. |
| Claims and completion | `contracts/concept-authority/behavioral-relations-v1.json`, `RelationAssuranceModel`, `validate_backend_conformance_report`, SEM-231 assurance material, `specs/formal/assurance-{policy,fulfillment}.yaml`, `docs/explain/reference/shared-semantic-integrity.md`, and relevant `docs/requirements/*/requirement.md` traceability. Retain each record's owner and evidence scope; documentation delivery does not promote a requirement. |
| Reader navigation and diagrams | `docs/public/participant-control.md`, `docs/public/backends.md`, `docs/public/limitations.md`, reference guides, `docs/explain/sdl/{sections,lineage,runtime-architecture}.md`, and existing composition diagrams. Public prose links to repository authorities; it must not include internal records into the published build. |

Unqualified reference filenames above are under `docs/explain/reference/`;
test filenames are under `implementations/python/tests/`. These are ownership
boundaries, not instructions to edit every listed file.

Concrete reconciliation hazards at this baseline:

- The public participant-control guide still describes mixed runtime execution
  as future work. #1018 now demonstrates simultaneous and staged arrangements
  with test providers. Preserve both that positive result and its limits.
- #1018 rejects reusable control combined with mixed execution and distributed
  dispatch combined with local portable mixed services. Separate successful
  rows do not establish their Cartesian product. Its mixed report deliberately
  has `passed: false`; the demonstration succeeds by checking expected results,
  including unsupported rows. Do not replace that report verdict with success.
- Migration guides contain earlier publication/adoption statements alongside
  later consumer updates. Separate historical delivery facts from current
  support. The reusable-control reference's blanket selected-delivery refusal
  also needs reconciliation against `ControlPlaneConfiguration` and #1368:
  installation can admit a matching compiled delivery binding, crossing owner,
  and `resolve_delivery_cut`. Unsupported joins still refuse; inspect the
  selected complete path rather than claiming all delivery works or none does.
- #1374 withdrew catalog backend statuses based on removed reference evidence.
  Keep execution basis, evidence origin, realization owner, declaration,
  realization claim, and conformance claim separate. Do not restore withdrawn
  claims from historical reports or from a runtime-mediated positive probe.

## Cross-cutting gates for executable guidance

Documentation itself adds no runtime surface. Its executable examples must
pass the same layers as any caller; using fixtures does not waive those gates.

| Layer | Required reuse and how guidance satisfies it |
| --- | --- |
| Source parsing and semantic validation | Use `raes.parse_sdl`/`parse_sdl_file`, bounded `load_sdl_yaml`, closed SDL models, `SemanticValidator`, composition/reference rewriting, and `compile_runtime_model`. Run complete examples, including semantic references; JSON/YAML parsing alone proves nothing about admission. No permissive loader, unchecked model construction, or duplicate validator. |
| Contract and context validation | Use published schemas, `ContractModel`, typed DTOs, and the existing occurrence, evaluation, crossing, inject, and history contextual validators. Resolve trusted pins, subjects, predecessor/results, scopes, and cuts independently of caller payloads. Schema-only acceptance does not execute `x-raes-invariants` or establish contextual truth. |
| Capability, profile, and config admission | Use API-407 support resolution, digest-bound selected manifests, backend protocol admission, `ControlPlaneConfiguration`, `MixedControlRuntimeBinding`, and `ParticipantControlRuntimeBinding`. Supply real typed installed owners and their compiler context. Declarations and callable method presence are not installed capability; preserve configuration refusals and whole-plan trial-control admission. |
| Authorization and information flow | Use `ControlPlaneIdentity`, role/subject/operation scope checks, exact-cut resolvers, crossing mediation, and final-sink policy. Recheck access before retry/readback. The original admitting principal owns effects; a drain caller lends no authority. No default operator credentials, participant access to administrative records, or disabling enforcement to make a sample work. |
| HTTP, when shown | Retain `ControlPlaneSecurityConfig.strict_defaults()`, the existing API auth and sealed route-authority inventory, bounded strict JSON ingress, and no-store responses. Preserve duplicate-key, depth, numeric and body limits. In-process examples do not require a new HTTP route or server. |
| Secret and environment shapes | Prefer credential-free typed harness injection. If an example needs SDL environment bindings, reuse `RuntimeEnvironmentVariable`/`GeneratedArtifactValueSource`: no literal plus `value_from`, no raw redacted/operator-secret value, and no generated value classified as operator-secret. Use `raes_contracts.secret_references` for logical secret references. Backend credential resolution stays downstream; never dump or hash an entire environment as provenance. |
| Host and files | Reuse the frozen repository Python environment and existing collector. Use fresh caller-selected local output roots outside the hashed source roots; refuse overwrite and close stores. No daemon discovery, new service, native lifecycle, or external upload. Never put tokens in process argv, shell history, filenames, copied output, or examples. |
| Exceptions, logs, and audit | Preserve `SDLParseError`/`SDLValidationError`, shared `Diagnostic`/`Severity`, stable diagnostic codes, `sanitized_failure_message`, and `require_audit_event_fields`. HTTP keeps its authorization/conflict/validation responses and redacted 500 envelope. Do not echo rejected inputs, raw backend exceptions, secrets, or hidden state. An unexpected exception cannot count as the expected refusal. No second exception hierarchy or logging pipeline. |
| Persistence and concurrency | Use `RuntimeSnapshot`, the operation ledger, `ControlPlaneStore.commit_participant_transition`, history validators, expected-head/revision checks, leases, and one-use dispatch claims. Read committed facts; retain indeterminate effects for authorized reconciliation. Examples must not mutate histories, reset budgets with new IDs, resend consumed claims, or infer exactly-once external effects. |
| Evidence and publication | Use shared conformance report validation/serialization and canonical JSON digests over explicit nonsecret inputs. Bind profile/config/source/case/cut and actual readback. A digest identifies bytes, not trust. Preserve capture pins and historical reports; source-bound new research uses `tools.research_capture` rather than rewriting numbered releases. |

Every executable example needs a named apparatus, entry point, expected
outcome, and evidence limit. Reuse existing fixture/harness cases through
targeted tests; installed product commands must not import repository tests.
Label parser/compiler examples as such. A documented expected refusal is a
valid example of unsupported recovery; it is not an executed recovery success.
Assertions should inspect terminal state and owner evidence, not just receipt
acceptance. No sleeps or printed success strings as proof of execution.

## Migration, extension seam, and non-goals

Migration guidance must identify producer/reader combinations and preserve
original bytes, policy content pins, keys, budgets, outcomes, and per-episode
interpretation. Unknown versions or missing historical context remain
unsupported/unverifiable. Never default them to the latest reducer or infer
new authority. Live policy/apparatus replacement must follow the incumbent
episode/operation lifecycle and explicit admission; durability grants no
permission for a new effect. Keep existing migration helpers and explicit
author decisions; do not invent a universal automatic converter.

The extension seam is the existing injected `RuntimeTarget`, exact
manifest/profile/contract support, typed control/inject owners, and conformance
harness parameters. Examples should expose the selected binding/profile,
case, and local output root rather than branch on backend names. Support rows
must identify the arrangement, pins, installed owners, evidence basis, and
limits. A future backend or profile supplies an admitted adapter/case through
that seam; it does not require rewriting a canonical schema or adding a second
support registry. Do not parameterize away fixed conformance expectations.

Keep current guidance current and historical records historical. Use a scoped
current-status pointer or the ADR-059 amendment process where needed; never
rewrite old decisions, captures, or completion evidence as if they had observed
today's behavior. The issue's older ASR-537 links do not create a requirement
for this run. Do not invent a requirement UID, edit generated requirement
status to claim completion, or transfer ownership of unrelated identity and
replay documentation. Link those owners only for the relevant boundary.

No runtime behavior, contract lineage, profile guarantee, scheduler, backend,
recovery engine, store, proof claim, or native qualification changes belong to
this documentation issue. No schema edits merely to accommodate examples.
If a real contract defect is exposed, record it explicitly for its owning
change; ADR-009/061 publication entries, hashes, fixtures, exports, packaged
corpus, and `schema_bundle()` parity still apply to any separately authorized
contract revision. Release tooling owns versions and changelog history.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, existing file-local repo policy,
and the relevant targeted example tests. `docs/public/conf.py`,
`tools/check_public_docs.py`, `tools/public_docs_guard.py`, `.vale.ini`, and the
existing `docs-local` lane govern public publishing; adding a reference note
outside `docs/public` does not publish it on the documentation site. Do not
copy internal trees into that build or use external hosting. Full tests,
integration, fuzz, completion, and broad policy suites remain CI work.
