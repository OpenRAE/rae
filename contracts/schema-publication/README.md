# Schema publication records

The root `contracts/schema-publication-manifest.json` is a stable index. Each
published contract owns one record under `entries/`; removals own independent
records under `tombstones/`. A record holds the contract identifier, the schema
path, and the stability. It holds no hash or change summary, so a schema change
does not edit its record. Git holds the schema history.

Record filenames match the contract identifier (or removed schema filename),
and the repository policy checker assembles and validates the complete catalog
deterministically.
