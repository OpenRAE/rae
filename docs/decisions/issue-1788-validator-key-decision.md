# Trial validator registry key decision

Status: accepted. The user selected the correction on 2026-11-15.

## Problem

The [public API design](issue-1825-public-go-api.md) fixes the consumer declarations.
The trial declaration currently has this key:

```go
type ConfigurationValidatorKey struct {
    ImplementationName, ImplementationVersion string
}
```

`Request.ParticipantConfigurationValidators` and `Request.ParticipantControlContextValidators` use this key.
The reference compiler selects a hook with the manifest registry owner's `validator_id` and `validator_version`.
It does not use the participant implementation's name and version.
These identities can differ.
These fields name the wrong owner.
A caller must not have to guess what they mean.

The binding is in `implementations/python/packages/raes_processor/trial_compiler/bindings.py`, in `entry_participant_configurations`.
The registry uses `BindingOwnerModel` in `implementations/python/packages/raes_contracts/contracts/experiment_bindings.py`.
The [preflight](issue-1788-experiments-trials-preflight.md) confirms this mismatch.

## Accepted correction

Correct the unreleased key declaration before its implementation:

```go
type ConfigurationValidatorKey struct {
    ValidatorID, ValidatorVersion string
}
```

Keep both request map names and their interface types.
Select both hooks by the manifest registry owner's exact validator ID and version.
Do not fall back to the implementation's name and version when the validator is missing.
Keep implementation identity checks in their existing manifest and configuration owners.
Keep selected-scenario control-context binding separate from registry selection.

This changes fields in the fixed Go API.
It changes no schema, digest, random draw, or Python behavior.
The experiment output stays the same.
Update the declaration and model in one change.
Update the typed API records and API guide too.
The changed architecture must pass `archcheck -design` before source implementation.

## Alternative that retains the fixed fields

Retain `ConfigurationValidatorKey` and both existing request maps.
Add a key that names the validator.
Add two maps that use this key.
Refuse inputs if the supplied maps disagree.
Never interpret the existing implementation fields as validator fields.

This keeps the fixed Go fields but adds two maps and a conflict rule.
The correction above needs less code.
The trial package has no code at the inspected baseline.

## Verification

Use different implementation and validator identities in a reference case.
Verify selection of only the exact registry-owner key.
Test missing IDs, changed versions, foreign owner results, and control-context pins.
Verify that a lookup failure returns safe diagnostics without a partial plan.
The declaration now uses the accepted key.
Behavioral tests must check the lookup when the trial compiler is implemented.
