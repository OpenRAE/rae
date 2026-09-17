# Evolution Governance

This directory contains normative RAES ecosystem policy for artifact
evolution: versioning, compatibility, deprecation, removal, and migration.

The governing decision is
[ADR-075](../../docs/decisions/adrs/adr-075-ecosystem-versioning-deprecation-and-migration-governance.md).

## Files

- [`versioning-deprecation-and-migration.md`](versioning-deprecation-and-migration.md)
  defines the normative surface-class matrix and rules for GOV-901, GOV-902,
  and GOV-903.
- [`deprecation-records.yaml`](deprecation-records.yaml) is the reviewable
  record surface for GOV-902 deprecation and lifecycle notices, validated by
  `tools/check_deprecation_lifecycle.py` against the complete-record contract.

- [`progressive-semantics.md`](progressive-semantics.md) defines explicit SDL
  revision selection and author-authorized migration for GOV-903.
