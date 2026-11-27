# Issue 1481: configurable runtime parameters architecture preflight

Recorded 2026-10-11. The supplied #1481 issue is the contract; there is no
formal requirement UID. This is design guidance, not an implementation plan
or a claim that the four external modules have been verified. Existing
ADR-078/105, SEM-218 and the recursive constraint specification govern; no
new ADR or parallel semantic authority is needed.

## Authority boundaries

Keep three facts separate: authored specificity, the selected parameter binding
and its derivation, and permission for backend realization. A typed configurable
string is not unknown knowledge or backend delegation. A substituted value must
not become an exact **author declaration** merely because it is concrete.
Defaults and required explicit inputs follow the same authority path, while
`BindingOrigin` continues to distinguish them. Collection closure is independent
of leaf parameterization; opening a scope cannot repair missing leaf authority.

The current gap crosses phase boundaries. `derive_instantiated_explicitness`
preserves constrained specificity; `_finite_domain_constraint` captures only
whole-field finite references; `_SourceMetadata._constrained_domain` requires
that captured enumeration. `Variable` has no string domain/pattern/length form.
`CapabilityConstraint` is specifically an allowed-values contract, not a general
substitution contract. Its provenance validator requires the selected input to
belong to that domain, and `InstantiatedScenario` requires the addressed concrete
field to equal that input (apart from incumbent capability normalization).
An interpolated address cannot satisfy that equality contract as written.

The supported form must explicitly distinguish a whole-field typed reference
from a derived string. Reuse `VariableType`, `ParameterBinding`, portable
explicitness, qualified identities and canonical substitution semantics. Any
additional derivation evidence belongs in the closed phase provenance carrier,
not Python private state, operation payload extensions or a second ledger.
It must survive nested import rewriting and independent serialized admission.
Verify declared input types, referenced bindings, concrete output and any retained
domain independently; never interpret the derived output as the parameter input.

Do not solve the missing domain by inventing example enumerations or publishing
the selected value as if it were the author's entire allowed domain. If typed
string-set authority is needed, extend the dependency-neutral domain algebra
and the specific recursive-domain union that needs it, with explicit membership
and relation semantics. The existing `NullableDomainDescriptor` versus legacy
`DomainDescriptor` separation is the incumbent for avoiding accidental expansion
of every capability envelope. A processor-derived concrete binding can use
existing literal/exact machinery only if its meaning is explicitly binding
selection, retains constrained author specificity and provenance, and does not
silently change existing finite-domain realization permission. This semantic
choice must agree in normative phase rules, schemas and admission before coding;
neither a blanket string wildcard nor unconditional promotion to exact is valid.

Embedded interpolation must preserve its relation to the selected domain.
`operator@` and `service@` are binding parts of the derived addresses, not
permission to choose any string. Reuse `_substitute_value`/`VARIABLE_TOKEN_RE`
semantics; do not add shell expansion, expression evaluation or a second template
language. Finite image domains must reflect the actual transformation, with
deduplication and existing resource budgets. Unbounded inputs must retain a
representable derivation or an explicitly selected derived binding, rather than
claim an exact finite image or drop the prefix relation. Multiple/repeated tokens
and import namespaces must not be misbound. Avoid Cartesian-product enumeration.

## Cross-cutting incumbents and gates

Python paths below are relative to `implementations/python/packages`.

| Layer and canonical incumbents | Required guardrail |
| --- | --- |
| Parse/composition: `raes.parser`, `SDLModel`, `SemanticValidator`, `instantiate`, `_composition_provenance`, composition budgets | Retain authoring validation, binding type/domain checks, concrete Pydantic reconstruction and semantic revalidation. Rewrite every parameter identity and field pointer through existing namespace helpers; preserve RFC 6901 escaping and source occurrence alignment. No unresolved tokens, unchecked `model_construct`, mapping-key substitution or new module resolver. |
| Phase shapes: `raes.phase_contracts`, `scenario.InstantiatedScenario`, `_scenario_instantiation`, canonical snapshot admission | Preserve `extra=forbid`, unique identities/pointers, binding existence, type-sensitive equality and closed phase separation. New derivation forms need their own applicable consistency check; do not disable whole-field equality globally. No `variables` or unresolved template tokens in instantiated artifacts, including provenance string values. Retained derivation data must respect that token scan. |
| Owning runtime models: application route models, `runtime_database`, `runtime_mail_service`, `runtime_values`, `validator/_runtime_mail` | Reuse existing path/name/address and cross-reference checks after substitution. A string type does not supersede an owner's validity rules or justify new path/domain/email regexes in the compiler. Distinguish omitted fields from authored defaults using existing presence metadata. |
| Classification and safe projection: `_classification_guard`, `realization_typed_runtime_projection`, `realization_concern_projections`, `runtime_values.enforce_observed_value_redaction` | `_runtime_scalar_constraints` deliberately skips classification-bearing records. Do not remove that guard to admit mailbox addresses. The owning typed projection must approve public address leaves while excluding raw credential/setting material; `credential_classification` is posture, not a credential. Protected values, commitments and presence markers keep their existing meanings. Parameter type alone never establishes publication safety. |
| Environment/config: `RuntimeEnvironmentVariable`, `ControlPlaneSecurityConfig`, existing model/config validators | Preserve `value`/`value_from` exclusivity, reference and sensitivity rules; do not generalize public mailbox/string support into permission to publish secret environment values. No new auth token, environment-binding or configuration shape is needed. |
| Compiler/shared semantics: `RealizationConcernDescriptor`, `RUNTIME_CONCERN_PROFILES`, `realization_recursive_constraints`, `realization_specialized_projection`, `raes_contracts.bounded_domains`, `realization_structure` | Use registered owner/projector metadata and source occurrence mapping. Preserve origins, required members, identities, exact siblings and local closure. Extend membership/composition/refinement/evaluation/compatibility together for any new domain; unsupported relations remain diagnostic-bearing, never approximated to success. Keep bounded traversal and pass-local metadata reuse. |
| Plan/admission: `realization_authority_materialization`, planner authority reconstruction/diagnostics, support/envelope diagnostics, `raes_contracts.realization_authority` | Publish the recursive constraint document and its canonical binding through the incumbent carrier. Serialized readmission must enforce the same demand. Keep backend support, apparatus defaults, configuration observation scope/strength and envelope feasibility separate. A bound checksum is integrity metadata, not authenticated authority or proof of execution. |
| HTTP/auth/runtime: `ProvisioningPlanModel`, `control_plane_api_models`, request-size guards, `control_plane_api/_auth`, trusted planner-plan digests, `backend_realization_authority`, direct backend adapter admission | Keep bounded closed DTO parsing, lossless conversions and existing target/role checks. Enforce demand before mutation on both direct and control-plane paths; caller-recomputed hashes do not attest planner origin. Reference/libvirt adapters consume portable authority rather than reinterpreting SDL. |
| Host/OS boundary: existing backend realization/driver boundaries | Configuration remains data. No planner shell commands, guest probes, secret argv or new ambient environment inputs. Path/database/address validation does not imply safe shell/SQL interpolation; retain driver-owned escaping and execution policy if these values reach execution. No live backend change is required by this planning fixture. |
| Observations/errors/storage: typed observation admission, `backend_calls`, snapshot sanitization, `Diagnostic`, `ApplyResult`, redacted API exception handlers, `control_plane_store*` | Retain shape, identity, scope/strength and manifest corroboration checks. Use existing error envelopes and safe concern/path diagnostics without raw inputs, domain alternatives, credentials or backend exception text. Sanitize success/failure before audit, receipts, history and persistence. Reuse existing canonical serializers/store reload; add no logger, exception hierarchy or constraint store. |

## Extensibility, contract governance and evidence

The extension seam is the registered concern's owning safe projection plus
typed provenance/domain dispatch, not a list of four kit names, parameter names
or backend-specific special cases. Another public scalar leaf or interpolation
should reuse that seam. Safety policy remains owner-specific; a generic walker
cannot infer it from field suffixes alone. Backend envelope sets and author input
sets retain separate semantics. No new controller/service/repository layer is
needed for this compiler and contract correction.

Published changes must follow ADR-009/061: review affected SDL phase/snapshot,
recursive-constraint and plan schemas, closed Python models, `schema_bundle()`,
fixtures, DTO converters and actual runtime consumers. Record publication
manifest/change-ledger entries and decide compatibility explicitly. Existing
readers must reject unsupported authority rather than silently ignore it.
Do not edit pinned ADRs, relax closed unions or hide semantics in extension data.

Reuse `test_sdl_phase_contracts`, `test_instantiated_scenario_schema`,
`test_api_424_composition_derivation`, `test_sem_218_explicitness`,
`test_issue_1200_mixed_runtime_constraints`, recursive carriage/normal-form tests,
`test_issue_1067_resolved_realization_authority`, runtime mail tests and existing
authority/observation fixtures. Evidence must cover all four issue cases with
additional values, required/no-default and default binding, both composed mailbox
addresses, literal/finite controls, invalid input and unsupported backend demands.
Also require nested composition and serialized scenario/plan admission, tampered
binding/output rejection, exact siblings, classified-value non-leakage and
malformed authority/observations. A manually completed authority fixture cannot
prove that compilation preserved authority. Planning fixture support declarations
do not claim backend execution or observed guest state.

Workflow incumbents are `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/check_repo_policy.py`, `noxfile.py`, `tools/nox_support`, `Makefile` and
`.pre-commit-config.yaml`. Use targeted local feedback and policy edit guards;
CI owns full suites. Use the requirement-free workflow rather than fabricating
a UID. Release-owned versions/changelogs and package layering remain unchanged.

Non-goals: implementing #1481 in this preflight; changing external env-packs;
adding a general regex/expression/constraint language; redesigning all variable
types, realization permissions, persistence or observation policy; weakening
backend admission; running deployments or live/integration suites; and adding
finite catalogs, per-kit exceptions or secret-bearing provenance to make tests
pass. Unsupported genuinely unsafe forms still fail closed with existing
`realization.authority-bound-unavailable` diagnostics; that fallback does not
satisfy the required public configurable string and mailbox cases.
