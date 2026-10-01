# ADR-026: Application HTTP Surface Inventory

## Status

accepted

## Date

2026-05-22

## Context

Issue #367 requires SDL expressivity for the participant-observable HTTP
application surface of a range service: route paths, methods, auth/session
requirements, request inputs, responses, template/static associations,
route-specific vulnerabilities, fixture secrets or diagnostic disclosures, and
redirect/error behavior.

The repository already has adjacent surfaces, but none owns this meaning by
itself:

- `Node.services` declares transport-level service bindings such as
  `tcp/8080`.
- `Node.runtime.network.published_ports` records host/OS publication of
  container ports.
- `Source.build`, `RuntimeFilesystemEntry`, and image source inputs record
  source files, templates, static files, and runtime file inventory.
- top-level `content` records scenario data or files placed into systems.
- top-level `vulnerabilities` records CWE-classified weakness definitions.
- participant observation boundaries record participant-specific visibility
  semantics, not the application route catalog itself.

The design risk is to overload one of those surfaces and make transport
services, source-code files, content fixtures, route inventory, authentication
state, vulnerability classes, and participant visibility all mean the same
thing.

## Decision

### 1. Model application route inventory as node-scoped runtime surface

HTTP application route/API/UI inventory belongs under the node-scoped runtime
surface, as typed observed application facts attached to `Node.runtime`.

The owning node is implicit from the enclosing node. The owning transport
service must be explicit on the application surface by referencing a declared
same-node `Node.services[].name` or its qualified `nodes.<node>.services.<name>`
form. A route inventory must not mutate `Node.services`, `infrastructure`,
`Source.build.config.exposed_ports`, or `runtime.network.published_ports`.

The initial surface should not add a new top-level `routes`,
`webapps`, or `applications` section. A future authored application intent
surface would need a distinct decision and must not reuse this runtime
inventory meaning accidentally.

### 2. Give routes stable identities separate from paths

Routes need stable route identifiers because paths are not stable symbols:
they may contain path variables, may be shared across HTTP methods, and may
change while the inventory fact remains comparable.

The route path is data. It must not be used as a mapping key. Prefer list
records with explicit `application_id` and `route_id` fields plus duplicate
validators. The canonical target form for route references should include the
owning node and runtime boundary, for example:

`nodes.<node>.runtime.applications.<application_id>.routes.<route_id>`

If the implementation publishes route refs into the generic named-reference
index, it must update semantic validation, module-composition namespacing, and
docs together so route refs survive imports and ambiguity checks.

### 3. Keep adjacent concepts separate

The route surface is placement and observation metadata for application-layer
behavior. It must reference adjacent surfaces instead of duplicating them:

- route `vulnerability_refs` point to top-level `vulnerabilities`; they do not
  define a second CWE schema.
- template and static associations point at same-node runtime file inventory,
  image source inputs, or source/runtime path fields; they do not embed file
  contents.
- fixture data that is genuinely scenario content belongs in `content`;
  template/source files do not become `content` merely because a route renders
  them.
- authentication requirements are observable application requirements, not
  control-plane authentication, API caller identity, or live session tokens.
- participant-specific visibility remains in `observation_boundaries`; route
  inventory records what the application exposes when observed.

### 4. Reuse existing SDL gates

The implementation must reuse the repository's existing gates:

- `SDLModel` closed-world Pydantic validation and field/model validators.
- parser key normalization, source-shorthand behavior, hashmap-key
  preservation, and variable-placeholder key rejection.
- shared parse helpers such as `parse_int_or_var()`, `parse_bool_or_var()`,
  `parse_runtime_enum_or_var()`, `absolute_path_or_var()` only for filesystem
  paths, and `coerce_string_list()`.
- `SemanticValidator` and `SDLValidationError` for cross-node, same-node
  service, vulnerability, file-association, and route-reference checks.
- `instantiate_scenario()` and `SDLInstantiationError` for substitution and
  concrete revalidation.
- `schema_bundle()`, `tools/generate_contract_schemas.py`, and
  `tools/check_generated_schemas.py`; generated schemas under
  `contracts/schemas/` must not be edited directly.
- existing `aces_processor.models.Diagnostic` and published control-plane or
  runtime envelopes if route facts later flow into snapshots, reports, or
  backend diagnostics.

No new parser, schema registry, validation framework, exception hierarchy,
logging stack, persistence mechanism, or backend-specific route dialect is
justified for this issue.

### 5. Validate application facts without leaking secrets

The model gate should validate the portable shape:

- route paths are URL paths, not filesystem paths; use a dedicated validator
  instead of `absolute_path_or_var()`.
- HTTP methods should normalize to one portable spelling and reject empty
  method lists.
- request inputs should be typed by location, such as path, query, header,
  cookie, form, JSON body, or uploaded file.
- response status codes should be 100 through 599 and content types should be
  explicit when known.
- redirects should keep target path/URL, status code, and condition separate.
- observable error/disclosure behavior should classify what is exposed rather
  than embedding raw stack traces, tokens, passwords, cookies, or backend
  inspect payloads.

Route-visible fixture secrets and diagnostic fields must reuse the existing
runtime sensitivity vocabulary, especially `plain`, `redacted`,
`secret_fixture`, `operator_secret`, and `unknown`. Redacted and operator-secret
values must omit raw values. Secret-fixture values may be represented only when
they are intentionally participant-visible fixture material and are safe for
examples, fixtures, diagnostics, generated schemas, logs, and snapshots.

### 6. Keep the extensibility seam application-scoped

The extension seam is the node-scoped runtime application surface. It should be
parameterized by protocol/application kind and owning service, not by Flask,
Django, Express, Rails, OpenAPI, HAR, or a specific scanner output format.

The next likely variations are virtual hosts, base paths, GraphQL, WebSocket,
gRPC-over-HTTP, framework-specific route names, richer auth policy, and scanner
evidence. Those should extend typed application or route submodels, or bounded
key/value evidence fields where appropriate, without creating a second route
schema elsewhere.

## Security and Validation Gates

- Parser gate: do not use route paths as mapping keys. If any native maps are
  added for headers, query parameters, MIME variants, or framework metadata,
  update only the necessary nested hashmap preservation entries. Avoid nested
  fields named `source` unless source-shorthand skip behavior is intentionally
  updated.
- SDL model gate: reject malformed URL paths, duplicate route ids, duplicate
  method/path pairs, malformed status codes, empty parameter names, and raw
  values where sensitivity classification requires redaction.
- Semantic validation gate: owning service refs must resolve to the same node;
  route vulnerability refs must resolve to top-level `vulnerabilities`; same
  node template/static refs should resolve to runtime filesystem inventory or
  source-input paths when those inventories are present.
- Instantiation gate: variable placeholders may stand in value fields, but not
  symbol-defining application ids, route ids, or mapping keys. Concrete
  instantiated scenarios must revalidate.
- Contract/schema gate: schema changes come from Python model sources and
  regeneration, never direct edits under `contracts/schemas/`.
- Host/OS exposure gate: host-published ports remain
  `runtime.network.published_ports`; route inventory must not hide externally
  reachable attack surface or duplicate host binding state.
- Runtime/control-plane gate: if route facts are reported through APIs or
  snapshots, use existing envelopes, authentication/authorization/audit
  behavior, request-size limits, idempotency patterns, and redacted error
  handling rather than raw backend payloads.

## Guardrails

- Do not add route data to `Node.services`; that surface is transport binding,
  not application behavior.
- Do not put route paths, redirects, or UI templates into
  `infrastructure.properties`.
- Do not create a route-local vulnerability class or duplicate CWE validation.
- Do not infer authentication state from committed cookies, bearer tokens, or
  process environment secrets.
- Do not embed raw Flask decorators, source-code snippets, stack traces, HAR
  captures, scanner JSON, request bodies, or uploaded-file contents as the
  portable SDL model.
- Do not make route ids globally scoped; route identity must include the
  owning node/application context.
- Do not add implementation logic under `implementations/python/src/aces/`;
  that tree is compatibility-only wrappers.

## Non-Goals

- Implementing issue #367.
- Updating `examples/scenarios/techvault.sdl.yaml`.
- Building a Flask, OpenAPI, HAR, crawler, scanner, or source-code discovery
  tool.
- Defining backend provisioning behavior for web applications.
- Redesigning `Node.services`, `content`, `vulnerabilities`,
  participant-observation boundaries, control-plane authentication, or runtime
  snapshot contracts.

## Consequences

### Positive

- Transport services, host publication, application routes, source files,
  fixture content, vulnerabilities, and participant visibility stay
  distinguishable.
- Existing SDL parsing, validation, instantiation, schema generation, concept
  authority, diagnostics, and control-plane envelopes remain authoritative.
- TechVault parity can represent participant-observable Flask routes without
  making Flask source syntax or scanner output the SDL authority boundary.

### Negative

- Route refs are longer because they include node and runtime ownership.
- Some facts may intentionally appear in adjacent places with different
  meanings, such as a template runtime file path and a route template
  association.

### Risks

- A top-level route section would make ownership and module namespacing easier
  to get wrong unless a distinct authored application concept is justified.
- A free-form route metadata dictionary would bypass closed-world validation
  and make redaction, cross-reference checks, and schema generation brittle.
- Overfitting to Flask would make the ACES surface poor at representing other
  HTTP applications, API gateways, reverse proxies, or scanner-observed
  surfaces.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-18 | #1298 | Separated extensible case-sensitive HTTP wire-method identity from controlled vocabularies while retaining legacy built-in aliases and execution boundaries. |

### HTTP method identity

Issue #1298 corrects the original closed nine-method interpretation. RFC HTTP
method identity is an extensible, case-sensitive wire token. It is therefore
owned by `RuntimeApplicationRoute.methods` and its published SDL schema, not by
the RAES governed-vocabulary extension syntax. The field accepts the non-empty
ASCII HTTP token grammar up to 128 characters, without trimming malformed
input. Whole-field method variables are authoring-only alternatives and must
pass the same token and duplicate checks after substitution.

Existing serialized uppercase built-ins remain stable. Lowercase and
mixed-case spellings of the nine historically admitted built-ins retain their
existing uppercase result as an explicit compatibility alias. All other valid
tokens, including `PROPFIND` and private tokens, retain exact case. Duplicate
method/path checks operate on the post-alias identities, so `get` and `GET`
collide while an extension token and a differently cased extension token do
not.

This changes neither the HTTP/HTTPS-only proxy-upstream profile nor any
observation, authorization, capability, selected-operation, or backend
execution contract. Implementations must not add HTTP methods to the
controlled-vocabulary catalog, encode them as `x-<owner>:<term>`, case-fold
extension methods, trim malformed input into a valid token, or make parser
acceptance imply backend support. See the focused
[issue #1298 architecture preflight](../../explain/reference/issue-1298-http-method-identity-preflight.md)
for the cross-cutting boundaries.
