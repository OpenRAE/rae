# Account Credential Bindings

This specification defines the portable relationship between a top-level SDL
account and credential material used to authenticate that account. It is the
normative account-credential contract for DSL-439 and issue #673.

## 1. Distinct concepts

An `Account` describes account existence and posture. Fields such as
`password_strength`, `disabled`, and `auth_method` MUST NOT be interpreted as
credential material.

A credential binding describes one authentication purpose served for its
owning account. The binding MUST be nested in that account's
`credential_bindings` list. It MUST NOT contain an account reference, target a
different account, or be inferred from a runtime value, environment variable,
path, backend option, username, or list position.

Credential material has exactly two v1 classifications:

- `secret_fixture` is deliberate scenario content and MUST carry a literal
  `value` in the authoritative SDL.
- `operator_secret` is operator-managed material and MUST carry only a safe
  logical `reference_id`; a resolved value MUST NOT enter SDL.

## 2. Structural contract

Each binding MUST contain:

- `credential_id`: a portable identifier unique within the owning account;
- `purpose`: `primary_authentication`, `administrative_authentication`, or a
  governed `x-<owner>:<term>` extension;
- `auth_method`: `password`, `key`, `certificate`, or a governed extension;
- `material`: the closed discriminated union above.

Unknown fields, an absent classification, a fixture without `value`, an
operator secret without `reference_id`, a mixed value/reference object, or an
unknown classification MUST be rejected structurally. Safe reference IDs are
bounded logical identities; URI locators, filesystem paths, commands,
environment-variable conventions, and provider objects are forbidden.

When bindings are present, exactly one binding MUST have purpose
`primary_authentication`; its method MUST equal the account-level
`auth_method`. `(purpose, auth_method)` pairs and `credential_id` values MUST be
unique within the account. Absence of `credential_bindings` declares no
portable credential material and implies no default or lookup convention.

## 3. Examples

```yaml
accounts:
  exercise-admin:
    username: admin
    node: web
    password_strength: weak
    auth_method: password
    credential_bindings:
      - credential_id: primary-login
        purpose: primary_authentication
        auth_method: password
        material:
          classification: secret_fixture
          value: deliberately-weak-fixture
      - credential_id: operator-bootstrap
        purpose: administrative_authentication
        auth_method: certificate
        material:
          classification: operator_secret
          reference_id: operator-secret.web-bootstrap
```

The first value is intentionally visible in the authoritative exercise
artifact. The second value is absent: its reference names operator-managed
material without locating or disclosing it.

## 4. Normalization, variables, and provenance

Known purpose and method spellings use the SDL case/hyphen normalization rules
and serialize canonically with underscores. Purpose, method, fixture value, and
safe reference ID MAY use an ordinary whole-field `${variable}` reference.
`credential_id` and `classification` MUST be concrete at authoring time.

Instantiation MUST reconstruct the closed union and rerun semantic validation.
Composition MUST retain each binding under its owning qualified account.
Fixture bytes and reference IDs MUST otherwise be preserved: implementations
MUST NOT trim, case-fold, Unicode-normalize, hash, mask, interpolate partially,
or parse them as another scalar type. Existing source ranges, composition
provenance, instantiation bindings, canonical account addresses, and
credential IDs are the binding's provenance; no competing provenance string is
authorable.

## 5. Compilation and capability admission

Compilation carries the binding inside the existing account placement; it MUST
NOT create a credential registry or second account resource. A plan containing
bindings exercises the governed provisioner account feature
`credential_bindings`. Compiler-produced and directly submitted plans MUST
reject a provisioner that does not advertise that feature before side effects.
Direct submission MUST reconstruct the canonical account shape and verify that
the payload account name matches its canonical account address.

Advertising the feature does not grant secret-resolution authority. Resolution
of an operator reference, native credential transformation, and independent
realization evidence remain backend-owned protected-sink behavior.

## 6. Information flow and inspection

Authoritative SDL, canonical SDL identity, and authenticated provisioning input
MAY contain a `secret_fixture` literal. Generic plan display, runtime snapshots,
operation records, apply-result details, diagnostics, logs, audits, exceptions,
and sanitized publication MUST be value-free for fixture values and operator
reference IDs. Rejected-request envelopes MUST NOT echo credential input.

For a credential-bearing plan, backend egress uses a closed result contract.
Account snapshot entries are reconstructed from the admitted plan and expose a
typed binding projection containing only `credential_id`, purpose, method,
classification, and value/reference presence. Arbitrary apply-result details
and backend-authored diagnostic prose are not admitted. Supplemental realization
data is limited to the existing typed provenance, observation, and envelope
carriers and closed evidence fields consumed by the applicable admitted
realization contract, including entry payload `artifact_satisfaction`. Such
evidence MUST pass its canonical structural and semantic validators, remain
bound to the admitted requirement and resource address, and survive projection
so that post-sanitization validation checks the same meaning. This permission
does not admit arbitrary payload additions or changes to plan-owned values.
See the [credential/artifact boundary guidance](../../docs/decisions/issue-1603-credential-artifact-evidence-preflight.md).
Applicable admitted realization concerns MAY replace plan values with observed
values at their registered payload paths. Their existing validators and safe
observation projections govern publication. OPEN choices, constrained choices,
and semantically equal EXACT observations follow their existing realization rules.
All payload values outside those paths and separately authorized evidence MUST
retain typed exact equality with the admitted operation.
The runtime MUST preserve observed meaning through repeat validation.
This permission does not change the canonical account credential projection.
See the [credential/observation design](../../docs/decisions/issue-1638-credential-realization-design.md).
A protected resolver or native transformer MUST keep
resolved and material-derived bytes outside `ApplyResult` entirely.

Projection follows the canonical account-placement `spec.credential_bindings`
path; a discriminator-shaped mapping elsewhere is not credential material.
Independent typed identities remain unchanged when their text happens to equal
a fixture value. Persistence and API publication consume the already-closed
snapshot and repeat only this structural path projection as an idempotent
defense.

A participant-visible fixture requires an explicit governed view rule naming
the exact canonical account address and `credential_id`, a disclosed visibility
and disclosure decision, an authorized participant audience binding, and the
existing marking, transformation, crossing-policy, audit, and provenance
evidence. `starting_accounts` and `interactive_access` establish eligibility
only; they are not disclosure authority. An operator-secret projection exposes
classification/reference presence only, never the reference ID or value.

## 7. Non-goals

This contract does not define a secret store, resolver protocol, backend
injection mechanism, credential generation or rotation, password hashing or
strength policy, MFA, credential discovery, or a participant credential route.
It does not merge top-level accounts with runtime local identities, directory
subjects, application principals, database roles, or participant identities.
