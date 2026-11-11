# Author participant control context

The optional `control_context_assets` section names existing ACT-620 descriptors.
Existing documents need no changes.
Empty additions retain their historical serialization and canonical identity.

Use `agents.<name>.control_context` for direct authored intent.
Use `behavior_specifications.<name>.control_context` for reusable participant selections.
Each slot contains `declaration_ref`, exact `asset_ref`, and optional `disposition`.
Use `control_context_asset_reference()` to obtain the descriptor's exact identity, version, and digest.
Do not infer the asset pin from its content checksum or locator.

Replace informal instruction strings in metadata with references to explicitly acquired immutable descriptors.
Keep private bytes in approved consumer storage.
This change provides no automatic conversion of historical metadata or delivery evidence.

For imported descriptors, preserve the complete external descriptor.
Use applicability that matches the final canonical participant address or its effective authored role.
Export the local asset symbol when an importer needs it.
Do not write private `__private` references or substitution tokens into descriptors.
Variables can select declaration references; normal pin and scope checks repeat after substitution.

For an ADR-094 participant factor, declare a literal-string target with a typed `control_context` domain.
The domain names the slot and pins every admitted declaration reference.
Configure a trusted contextual owner validator through the existing complete-configuration hook.
Missing contextual validation rejects admission.
Direct, reusable, and factor selections cannot compete for the same participant slot.

Read the typed `control_context_selection` from the admitted configuration.
Retain it through serialization and pass it to the run producer.
Do not resolve its string against a newer catalog or substitute current defaults.
Selection remains intent, without proving visibility, authorization, or delivery.
Use ACT-620's trusted lifecycle, authority, content, and exposure checks before release.

See the [examples](../../../examples/scenarios/participant-control-context/README.md)
and [normative contract](../../../specs/sdl/participant-control-context.md).
