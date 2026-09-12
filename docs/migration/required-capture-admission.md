# Required Capture Admission Migration

Issue #1112 changes capture support from descriptive capability discovery to a
fail-closed execution contract.

Backend manifests that may execute SDL `evidence_requirements` or experiment
capture specifications must publish `capabilities.observation.capture_offers`.
Each offer is atomic: it binds the output contract and fields to the artifact,
media, capture, source, scope, channel, window, integrity, sensitivity,
availability, fidelity, disclosure, retention, and export terms that are
actually supported. Legacy `supported_*` lists remain discovery summaries and
are not an admission fallback. A manifest with no matching offer is rejected
before effects. The in-repo stub and reference-emulation manifests deliberately
publish no capture offers because their runtimes do not implement the promised
artifact production path; tests that exercise admission declare narrow,
scenario-specific offers explicitly.

Offers for SDL requirements that use `scope_refs` must enumerate the exact
authored targets in `scope_refs`; `*` is rejected. Trial compilers resolve
scenario-family variables before matching these and all other capture terms.

SDL authors should add `output_contract` and `field_selectors` whenever an
authored evidence requirement is intended to execute. Existing requirements
that omit both fields remain structurally readable, but they cannot make a
field-level output promise. Precise installation declarations do not imply a
capture requirement.

Trial compilers must acquire every referenced capture-spec payload and include
its digest in `admitted-trial-plan-v1.input_refs.capture_spec_refs`. Missing,
substituted, ambiguous, or unsupported capture specs fail admission. Trial
realization supplies the same exact payloads and rechecks the selected backend.

Run consumers that make evidence-satisfaction claims use
`validate_experiment_run_evidence()` with exact capture specs, evidence records,
and bounded byte readers. The validator does not fetch URIs. It checks the
artifact identity, byte count, checksum, media and role, required integrity,
the authoritative `output_contract` schema and owning semantic model, RFC 6901
field selectors, required redaction state, and sensitivity across requirement,
record, and artifact. Study conditions that require evidence consume the same
validated requirement-to-artifact bindings.
Historical `satisfies_refs`, payload summaries, and backend assertions remain
metadata; they are not proof of emitted content.
