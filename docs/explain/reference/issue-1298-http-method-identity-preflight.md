# GOV-922 / issue 1298: Extensible HTTP method identity preflight

Architecture preflight for 2026-09-18. This note narrows the implementation
boundary for issue #1298. It does not implement the change, define backend
WebDAV support, or create a new concept-authority surface.

## Decision and ownership

`RuntimeApplicationRoute.methods` is a collection of HTTP wire-method
identities. It is not a closed RAES enum, a governed `x-<owner>:<term>`
vocabulary, an application capability list, an authorization grant, or an
executor operation selector. The owning contract remains ADR-026 and
`raes/runtime_application.py`; the published SDL schemas must express the same
shape for schema-only consumers.

One field-owned parser must implement the RFC token grammar and the compatibility
rule. The portable grammar is the non-empty ASCII HTTP `token` character set,
bounded to 128 characters per method identity; whitespace, separators outside
that set, non-ASCII, control characters and overflow are invalid. Validation
must not trim input into validity. Whole-field `${variable}` references remain
an authoring-only alternative and are revalidated after substitution. Keep the
128-character bound at this field-owned grammar/schema seam so a future
evidence-backed widening changes one contract rather than scattered consumers.

The compatibility rule is intentionally asymmetric:

- any case spelling of the nine formerly admitted names (`GET`, `HEAD`,
  `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE`, `PATCH`) maps to the
  existing uppercase identity;
- every other valid method token is retained exactly, including case; and
- duplicate method/path detection runs after that alias mapping. Thus `get`
  collides with `GET`, while `PROPFIND` and `PropFind` remain distinct.

Do not broaden the alias set when another method becomes common. A future
compatibility alias is an explicit migration decision, not registry growth.
List ordering remains the existing document ordering; do not introduce an
unrelated digest migration by sorting methods.

## Canonical incumbents to reuse

| Concern | Existing owner and required treatment |
| --- | --- |
| Model and field validation | `RuntimeApplicationRoute`, `coerce_string_list()`, `is_variable_ref()` and `SDLModel` (`extra="forbid"`). Keep the HTTP-token helper local to the HTTP application boundary unless another actual HTTP token field needs the identical contract; do not route this through `GovernedVocabulary`, `parse_runtime_enum_or_var()` or the concept catalog. |
| Route uniqueness | `RuntimeApplicationSurface.validate_surface()` owns route-id and method/path collisions. Compare the normalized method identity and exact path here; do not add a second collision index in parser, compiler or validator. |
| Source ingress | `_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py`, `parser.py` and `_model_diagnostics.py` already provide safe YAML, duplicate-key detection, source limits, structural construction and bounded source diagnostics. Validator messages must describe the rule without echoing the rejected token. |
| Variables and concrete admission | `instantiate.py::_substitute_value()`, `_BoundScenarioContent`, `InstantiatedScenario.model_validate()`, `admit_instantiated_scenario()` and `_safe_model_validation_errors()` already substitute then structurally and semantically revalidate. Do not special-case method variables in the substitution engine. |
| Module composition | `raes.composition` expands models through existing closed scenario models. Method values are not identifiers to namespace and must pass through unchanged before ordinary model revalidation. |
| Compilation and comparison | `realization_runtime_concern_profiles.py` and `realization_typed_runtime_projection.py` own the `runtime-applications` projection; `realization_recursive_constraints.py` and `raes_contracts.realization_structure` own recursive comparison. Preserve exact post-alias scalar identity; do not introduce a compiler-only method map or silently case-fold observed values. |
| Canonical snapshots | `canonical.py`, `InstantiatedScenarioSnapshot`, RFC 8785 serialization and `canonical_instantiated_sdl_digest()` own canonical bytes and snapshot admission. Round trips must preserve extension case. The compatibility alias happens before canonicalization, never during digesting or legacy snapshot migration. |
| Published schemas | The hand-governed files under `contracts/schemas/` are normative; `raes_contracts.contracts.bundle::schema_bundle()`, `tools/generate_contract_schemas.py` and `tools/check_generated_schemas.py` must produce identical output. Authoring schemas allow token-or-variable; instantiated, snapshot and materialized schemas allow only concrete tokens. Express non-empty collections, item grammar, the chosen length bound and uniqueness wherever JSON Schema can enforce them. |
| Schema publication | Every changed published schema needs its matching `contracts/schema-publication/entries/*.json` `last_change` summary and content hash, checked by `tools/check_schema_publication.py`. Do not hand-change a schema without its model/source parity and ledger entry. |
| Errors and diagnostics | Reuse `SDLParseError`, `SDLValidationError`, `SDLInstantiationError`, `_model_diagnostics.py`, `Diagnostic` and `portable_diagnostic_payload()`. No new exception hierarchy or HTTP-specific error envelope. Parser and instantiation errors must remain bounded and value-free because some control-plane conflict paths expose `str(ValueError)`. |
| Workflow | Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, `tools/verify_all.py` and the configured nox checks. This is GOV-922 work; Release Please owns `CHANGELOG.md` and the version. |

## Cross-cutting security and runtime layers

| Layer | Guardrail |
| --- | --- |
| YAML/JSON and config shape | Preserve UTF-8/input/depth/node/alias limits, safe YAML, duplicate key/member rejection, strict model keys and whole-field variable grammar. Direct Pydantic and schema-only ingress must enforce the same method item grammar; scalar-to-list compatibility may reuse `coerce_string_list()` but must not split, strip or uppercase extension tokens. |
| Authentication and authorization | Route inventory is descriptive input and creates no control-plane principal, entitlement, route access, selected operation or backend permission. Existing `ControlPlaneSecurityConfig`, API `_auth.py`, planner authorization and operation admission remain unchanged. |
| Sensitive values and environment | A method token is not a secret reference, environment binding, URI or command. Do not consult environment variables, files, registries or networks while parsing it. Invalid-token diagnostics and audit reasons must not reproduce attacker-controlled values. Existing route disclosure/exposed-field sensitivity and redaction rules remain intact. |
| OS/process exposure | Method acceptance must never construct argv, shell text, executable names, imports, paths or backend handler selection. Any later executor support must use its existing fixed invocation/config interface and explicit backend capability plus selected-operation admission; credentials stay out of argv, logs and errors. |
| Error envelopes and observability | Keep `_model_diagnostics.py` escaping/bounds, `_safe_model_validation_errors()` value-free projection, API redacted request errors, bounded audit queues and stable diagnostic envelopes. Log only stable reason/code and owned address, never the supplied method value or raw model payload. No new telemetry is required. |
| Persistence | No new store, migration table, cache or registry is warranted. Authored, instantiated and materialized documents plus canonical snapshots use their existing codecs. Historical uppercase built-ins retain meaning; do not rewrite stored digests or teach the legacy snapshot migrator a current-model normalization. |

## Contract and compatibility guardrails

- Use one grammar/normalization owner to drive Python and generated JSON Schema;
  do not maintain independent regexes in tests, parser, compiler and schemas.
- Schema acceptance must agree with direct model construction, parsing,
  instantiation and snapshot admission, including full-string anchoring and
  trailing-newline/control rejection.
- Preserve `route_id`, URL-path validation, non-empty method lists, duplicate
  route ids, duplicate post-alias method/path bindings, parameter/response
  bounds, legacy-classification rejection, sensitivity controls, same-node
  service validation and proxy-upstream agreement.
- Preserve the deliberately narrow `RuntimeApplicationRouteUpstreamScheme`
  HTTP/HTTPS enum. It describes the proxy-to-origin scheme and is not evidence
  that route methods are closed.
- Parser acceptance means only that an observed method can be represented and
  compared. It proves neither observation, application support, authorization,
  backend capability nor successful execution.
- Validate the two important negative spaces: invalid token characters must not
  be repaired, and valid extension identities must not be squeezed through the
  governed-vocabulary `x-<owner>:<term>` grammar.

## Required conformance boundaries

The focused regression surface must exercise authoring parse/direct model,
variable substitution and post-substitution rejection, file-backed composition,
instantiated admission, runtime-applications projection/comparison, canonical
serialization and snapshot round trip, plus Python/schema agreement. It must
cover `PROPFIND`, two valid private identities differing only by case, legacy
built-in aliases, empty and duplicate lists, post-alias binding collisions,
whitespace/control/non-ASCII/separator failures, the length bound, and
value-free diagnostics. Existing proxy, path, route-id, service-reference,
disclosure/redaction and selected-operation tests are regression boundaries,
not behavior to replace.

## Non-goals and anti-patterns

- No HTTP-method controlled-vocabulary catalog or `Enum`.
- No `x-<owner>:<term>` spelling for wire tokens and no generic extension bag.
- No WebDAV provisioning, request dispatch, scanner, route probing or automatic
  observation.
- No claim that a backend can execute every admitted method.
- No redesign of application protocols, proxy upstreams, service bindings,
  published ports, authorization, vulnerabilities or participant visibility.
- No new parser, schema registry, canonicalizer, comparison engine, exception
  hierarchy, logger, API route, persistence layer or workflow.
- No silent rewrite of historical snapshots/digests and no sorting migration
  hidden inside this identity correction.
