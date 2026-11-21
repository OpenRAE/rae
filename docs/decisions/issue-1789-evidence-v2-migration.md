# Satisfiability evidence v2 migration

The satisfiability service and CLI now return evidence v2. This is a breaking
change. Python previously emitted internal workflow names that its published
JSON schema rejected. The new version emits `then`, `else` and `default`.

| Part | Previous version | New version |
| --- | --- | --- |
| Evidence schema | `scenario-satisfiability-evidence-v1` | `scenario-satisfiability-evidence-v2` |
| Evidence profile | `scenario-satisfiability-evidence/v1` | `scenario-satisfiability-evidence/v2` |
| Witness profile | `raes-satisfiability-witness/v1` | `raes-satisfiability-witness/v2` |
| Snapshot schema | `instantiated-scenario-snapshot-v1` | `instantiated-scenario-snapshot-v2` |
| Snapshot profile | `raes-sdl-instantiated-snapshot/v2` | `raes-sdl-instantiated-snapshot/v3` |

Select the new schema when validating new service results. In Python, use
`ScenarioSatisfiabilityEvidenceV2Model` from `raes_contracts.satisfiability`.
Read workflow targets from `then`, `else` and `default` in returned JSON.
The authored SDL names and the satisfiability outcomes keep their meanings.

All new satisfiability results carry the new evidence profile, including
unsatisfiable and unsupported results. All new satisfiable results carry the
new snapshot profile. Their snapshot hashes change because the version is part
of the hashed document, even when the scenario contains no workflows.

Keep stored v1 records with their original schema, profile and digest. The
existing Python `ScenarioSatisfiabilityEvidenceModel` and historical canonical
functions retain their old behavior. The current service replay compares v2
results; it does not silently upgrade old records. Re-run the source analysis
to create a new v2 record. Retain the old record separately when evidence
history is required. A renamed document must not retain its previous digest.

The old schemas remain published. The new Go transport records are
`binding.ScenarioSatisfiabilityEvidenceV2` and
`binding.InstantiatedScenarioSnapshotV2`. Existing Go binding types remain.
This change does not switch the exploit-path service or other snapshot users
to the new version.

The Go `sdl.AdmitSnapshotWithContext` reader accepts v3 snapshots and checks
their digest through native admission. Legacy migrations remain limited to v2.
