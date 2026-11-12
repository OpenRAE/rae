# SDL semantic vectors

This published fixture family supplies reviewed SDL inputs and expected semantic results.
Its format is `raes-sdl-semantic-vectors/v1`.
The initial publication retains 824 cases in nine shards.
The [maintenance guide](../../../../docs/develop/sdl-semantic-fixtures.md) gives the update procedure.

## Files and inventory

`semantics.json` lists the ordered shards and the total case count.
Each shard entry gives its basename, case count, and unprefixed SHA-256 hash.
The hash covers exact file bytes, including whitespace and the final newline.
Shard names start at `semantics-000.json` and increase by one.
Each shard contains a JSON array of cases.

Each shard and the manifest have a 450 KiB byte limit.
The reader accepts at most 128 shards and JSON nesting depth 64.
Case counts are positive, and case names are unique across the family.
Missing, extra, unsafe, malformed, or changed shards fail the inventory check.

`semantics-provenance.json` records the original Python source revision, package hash, and dependency versions.
This file is historical evidence.
It does not require a current Python installation or a package-hash update.
Repository history records later reviewed fixture changes.

## Case records

| Field | Meaning |
| --- | --- |
| `name` | Stable, unique case name |
| `source` | SDL source text, decoded as `main.yaml` |
| `accepted` | Expected semantic admission result after construction |
| `findings` | Ordered semantic findings, with recorded message, owner, and pointer |
| `locations` | Source records aligned with findings; unowned locations can be null |
| `advisories` | Ordered warning messages |
| `canonical`, `digest` | Expected canonical bytes as a string and their `sha256:` digest after admission |
| `canonical_error` | Historical exception label for a canonical-domain refusal after admission |
| `admission_error` | Historical description of the portable-bounds refusal before semantic checks |
| `materialized` | Optional metadata identifying materialized SDL; the document owner determines its actual phase |
| `record_explicitness`, `explicitness` | Optional value-free explicitness expectations |

All cases require `name`, `source`, `accepted`, `findings`, `locations`, and `advisories`.
Optional fields apply only to their corresponding result.
Unknown fields and unsupported settings fail the reader.
Expected negative SDL results are distinct from malformed fixture records.

The native runner checks admission, ordered finding messages, source locations, warning messages, explicitness, canonical bytes, and semantic digests.
Its location checks preserve the existing mixed-control pointer refinement.
It does not directly compare every recorded diagnostic field, including each finding's `owner` and `pointer`.
The retained location metadata also includes code, message, severity, stage, and canonical address.
Those fields do not expand the existing comparison claim.

The `SDLParseError` label in `canonical_error` describes the original Python recorder.
The Go runner checks refusal of canonical bytes and digest, without requiring a Python exception type.
The portable-bounds case instead requires `sdl-materialized-portable-bounds` before semantic findings.

## Authority and distribution

The SDL specifications define semantic meaning.
These fixtures provide finite conformance evidence; they do not prove complete SDL conformance or runtime safety.
Maintainers review expected results against those specifications.
They do not regenerate expectations from the implementation under test.

`internal/sdl/authoring` owns the native inventory and semantic tests.
The existing `contractgen` tool includes this family in the embedded contracts corpus.
The packaged copy is derived from these files.
Retained Python parity readers consume this directory but do not maintain it.
