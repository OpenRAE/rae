# Stateful realization resources

`generated_artifacts` and `persistent_volumes` are portable provisioning
desired state. They describe prerequisites a stateful service consumes; they
are not observations of mounts already present on a running node and they are
not provider-specific Compose fragments.

Every declaration has a user-defined identifier and compiles to one stable
provisioning address:

- `generated_artifacts.<id>` becomes
  `provision.generated-artifact.<id>`;
- `persistent_volumes.<id>` becomes
  `provision.persistent-volume.<id>`.

## Generated artifacts

A generated artifact declares a `certificate_bundle`, `rendered_config`,
`ssh_key_bundle`, or `random_value` generator, its regeneration lifecycle,
non-secret provenance, the complete output set, and every consumer.
`ssh_key_bundle` is generated SSH key/access material; it is separate from X.509
certificate bundles and runtime SSH server configuration. `random_value` is a
freshly generated random value described by a typed recipe (see
[Random values](#random-values)).

Each output carries a contained relative path, a sensitivity class (`public`,
`restricted`, or `secret`), and a distribution disposition:

- `consumer_selected` allows read-only projection to consumers that name the
  output in `selected_outputs`;
- `producer_private` keeps the output within backend-owned producer state and
  cannot be selected by a consumer.

SSH artifact consumers must select at least one declared, non-private output.
Selections are unique, and every `consumer_selected` SSH output must be selected
by at least one consumer. Existing certificate/config declarations that omit
`selected_outputs` retain their compatibility meaning: all non-private outputs
are available to that consumer. An explicitly present selection must contain at
least one output; an empty list is invalid. New declarations should select
outputs explicitly.

For example, one SSH artifact can keep a private key producer-private while
projecting only its public forms:

```yaml
generated_artifacts:
  operator-access:
    generator: ssh_key_bundle
    lifecycle: regenerate_on_change
    provenance: access/operator-ssh.yml
    outputs:
      - name: private-key
        path: id_ed25519
        sensitivity: secret
        disposition: producer_private
      - name: public-key
        path: id_ed25519.pub
        sensitivity: public
        disposition: consumer_selected
      - name: authorized-keys
        path: authorized_keys
        sensitivity: restricted
        disposition: consumer_selected
    consumers:
      - node: bastion
        mount_destination: /run/raes/ssh
        access_mode: read_only
        selected_outputs: [public-key]
      - node: workstation
        mount_destination: /home/operator/.ssh
        access_mode: read_only
        selected_outputs: [authorized-keys]
```

The contract contains desired metadata only; key values and rendered bytes
never enter SDL, plans, snapshots, diagnostics, or provenance. Output paths use
one canonical POSIX relative-path spelling. Generated artifacts are immutable
inputs to consumers; every consumer therefore declares `read_only` access.
Output selection changes only a consumer projection: generation, lifecycle,
provenance, dependencies, reconciliation, and deletion remain artifact-wide.

## Random values

A `random_value` generated artifact declares a portable, value-free **recipe**
for a freshly and unpredictably generated value (for example a CTF flag). The
backend owns cryptographically secure generation; the SDL carries only the shape.

A `random_value` artifact declares exactly one output and both a `random_value`
recipe and a `regeneration_scope`; neither field is valid for any other
generator. The recipe declares:

- **Alphabet:** exactly one of a named `alphabet` (`hex_lower`, `hex_upper`,
  `digits`, `alpha`, `alphanumeric`, `base32`, `base58`) or a `custom_alphabet`
  string of unique, non-whitespace, non-control characters.
- **Size:** exactly one of `length` (random character count) or `entropy_bits`
  (target entropy budget). A `secret`-sensitivity output requires at least 128
  bits of effective entropy; the literal wrapper contributes none.
- **Format (optional):** a bounded `prefix`/`suffix` literal wrapper, e.g.
  `TECHVAULT{<32 hex>}`. The fully rendered value is bounded.
- **min_entropy_bits (optional):** an explicit author-declared entropy floor.

`regeneration_scope` governs freshness, distinct from the `lifecycle` reuse
policy:

- `per_run` — a fresh value for each authoritative run; resume/retry within a run
  retains it. Requires a run identity, or admission fails before mutation.
- `per_instantiation` — a fresh value per realized scenario instance; runs
  reusing that instance retain it. Requires an instantiation identity.
- `once` — one generation for the artifact instance's lifetime.

A recipe change within an active scope is a real change and reconciles as an
update; an ordinary refresh never silently rotates a live value.

```yaml
generated_artifacts:
  techvault-flag:
    generator: random_value
    lifecycle: reuse_valid
    regeneration_scope: per_run
    random_value:
      alphabet: hex_lower
      length: 32
      format: {prefix: "TECHVAULT{", suffix: "}"}
    provenance: techvault/ctf-flag
    outputs:
      - {name: flag, path: flag.txt, sensitivity: secret}
    consumers:
      - node: web
        mount_destination: /srv/flag
        access_mode: read_only
        selected_outputs: [flag]
```

The realized value never enters the SDL, plans, snapshots, diagnostics, audit, or
provenance.

## Generated-artifact delivery modes

A generated-artifact output reaches a consumer through one of four portable
**delivery modes**:

- `mount` — the read-only file projection declared directly on
  `generated_artifacts[].consumers[]` (above); this is the default and only mode
  authored on the artifact.
- `environment` — one node process-environment variable, declared on
  `nodes.<node>.runtime.environment[]` with a value-free `value_from`
  reference to a generated-artifact output *instead of* a literal `value`.
- `env_file` — an opaque env-file input, declared on
  `nodes.<node>.runtime.environment_files[]` with a `value_from` reference. RAES
  treats the file as one runtime environment input and does not parse or compare
  its individual key/value entries.
- `content_text` — a generated value rendered into a content placement's text at
  backend materialization time, declared on `content.<name>.text_from` (a
  value-free reference) *instead of* a literal `text`. Only file content may use
  `text_from`; a `secret` output requires the content to be marked `sensitive`.
  The compiler derives the matching consumer projection and an ordering edge onto
  the producing artifact.

`environment` and `env_file` bindings are authored **once**, on the node's
runtime environment; the compiler derives the matching generated-artifact
consumer projection into the provisioning resource. Authors never duplicate the
binding under `generated_artifacts[].consumers[]`. Because an artifact may be
consumed only through environment bindings, its authored `consumers` list may be
empty — but semantic admission still rejects an artifact that no file consumer
and no environment binding consumes.

A `value_from` reference names the producing `generated_artifacts.<id>` (bare id
or namespaced form) and one of its outputs; it carries no bytes. The referenced
output must resolve unambiguously, must exist, and must not be `producer_private`.
The realized value never enters the SDL, plans, snapshots, diagnostics, audit, or
HTTP envelopes: a generated *secret* environment value omits any raw `value` and
is classified `redacted`. `operator_secret` is **not** used for generated
material — it remains reserved for out-of-SDL operator-controlled secrets.

A provisioner declares each delivery mode it can realize in
`supported_generated_artifact_delivery_modes`; supporting generated artifacts
implies at least `mount`. Admission rejects a binding whose delivery mode the
backend does not claim, so a backend cannot silently downgrade an environment or
env-file injection into a file mount. A runtime-generated value may become
available only after its producer boots; a consumer reference does not imply an
ordering edge, so declare `ordering_dependencies` / `refresh_dependencies` where
the value must exist before a dependent process starts.

## Persistent volumes

A persistent volume declares `retain` or `ephemeral` lifecycle, portable
single/multi-writer access semantics, and every consumer. Consumers name a
declared non-Windows node, a canonical POSIX absolute mount destination below
`/`, and read-only or read-write access. `read_write_once` admits at most one
writer node. A node and mount-destination pair may be owned by only one
generated artifact or persistent volume.

## Graph and realization rules

Both resource kinds may carry addressable `ordering_dependencies` and
`refresh_dependencies`. References must resolve across the combined stateful
resource set. Ordering dependencies must be acyclic. Reference and graph
validation completes before provisioning operations are dispatched.

## Deferred verification of generated values

An `observed_state` string proposition may compare a submission against a
generated value without the value appearing in the SDL. Its `string` predicate
declares a value-free `expected_from` reference to a `generated_artifacts.<id>`
output (a scalar `equals`/`not_equals` operator, mutually exclusive with a literal
`expected`). The evaluator resolves the value at the same run scope and compares
inside the protected backend; the expected value never enters the SDL, plan,
evidence, or error envelopes, and a `producer_private` output cannot be selected.
A backend declares this in its evaluator capability
`supports_deferred_expected_comparison`, and admission rejects an `expected_from`
predicate a backend does not support.

The compiler preserves each declaration as an exact SEM-218 realization
requirement and emits its typed payload into the provisioning plan. Backends
must either honor the complete declared resource or reject the plan; silently
substituting an observed mount, generic content placement, or provider-private
configuration is not conformant. A provisioner that supports generated
artifacts also declares every supported generator in
`supported_generated_artifact_kinds`; the coarse support flag alone does not
authorize an unlisted kind.

Published JSON Schemas reject exact duplicate collection members. Relational
uniqueness, cross-resource reference resolution, mount ownership, and access
cardinality are published as `x-raes-invariants` and enforced by semantic SDL
admission; JSON Schema success alone is not semantic admission.
