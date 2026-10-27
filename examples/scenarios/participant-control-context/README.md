# Participant control-context references

These examples declare reference-only instruction, directive, policy, and guidance assets.
They contain synthetic public descriptors, without private content bytes.

- `context-kit.sdl.yaml` selects a shared instruction for red and withholds it from blue.
- Blue also selects a distinct policy in the `rules` slot.
- A reusable specification selects directive version `two` for red's `followup` slot.
- The guidance declaration has no selection.
- `twice-imported.sdl.yaml` imports the kit as `alpha` and `bravo`.

Each import retains the same immutable descriptor and asset pin.
Participant addresses and local declaration references receive their own namespaces.
The descriptor uses effective role applicability, which remains valid across these imports.
An address-scoped descriptor must already name its final canonical participants.

Declaring or selecting an asset creates no participant-visible item or content placement.
`withheld` states authored intent; it is not a runtime withholding or delivery record.
Different slots imply no ordering, precedence, or instruction composition.

An ADR-094 participant target can declare a `control_context` domain:

```yaml
context.briefing:
  target_id: context.briefing
  value_type: string
  allowed_value_kinds: [literal]
  sensitivity: restricted
  control_context:
    slot_id: briefing
    references:
      control_context_assets.alpha.shared:
        asset_id: privacy-instruction
        asset_version: one
        asset_digest: sha256:83c7094c1ac208ad0b6cbe65560801b2512b93edf919b3b4e1debf6ae6eada8a
```

A participant factor selects the literal `control_context_assets.alpha.shared`.
Use a participant and slot with no competing SDL selection.
The selected manifest owns the target and pins this domain.
Configure the trusted `SDLControlContextConfigurationValidator` through the existing owner-validator hook.
The compiler binds it to each concrete trial scenario before it seals the configuration.
The result retains a typed selection and exact asset pin for the run producer.

The consumer must still validate lifecycle, authority, content, audience, and delivery under ACT-620.
See the [normative reference contract](../../../specs/sdl/participant-control-context.md)
and [migration guidance](../../../docs/explain/sdl/control-context-migration.md).
