# Contract type conversion findings

The Python models accept some values that their published schemas reject.
The schema checks and Python model checks below used the same fixture bytes and one changed value.
Python code and published schemas remain unchanged.

| Contract and field | Supplied value | Schema accepts | Python accepts | Python result |
| --- | --- | --- | --- | --- |
| `random-stream-profile-v1`, `/root_entropy/byte_length` | `"32"` | No | Yes | `32` |
| Same field | `32.0` | Yes | Yes | `32` |
| Same field | `true` | No | Yes | `1` |
| `participant-execution-service-state-v1`, `/capacity` | `"4"` | No | Yes | `4` |
| Same field | `4.0` | Yes | Yes | `4` |
| Same field | `true` | No | No | Rejected |
| `operation-receipt-v1`, `/accepted` | `"true"`, `"false"`, `"yes"`, `"on"`, `1`, `0`, `"0"` | No | No | Rejected |

The source fixtures are:

- `contracts/fixtures/profiles/random-stream-profile-v1/valid/blake3-xof-v1.json`
- `contracts/fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json`
- `contracts/fixtures/control-plane/operation-receipt-v1/valid/accepted.json`

Draft 2020-12 treats an integral JSON number such as `32.0` as an integer.
A string or Boolean does not satisfy an integer schema.
The operation receipt model uses strict Boolean validation.
The Go structural checker currently follows the published schema in each case.

## Maintainer decision

On 2026-11-03, the maintainer selected option 1: require the published schema types.
The recorded reply was `1.` to the choice between schema types and Python conversions per field.
Go rejects values accepted only through implicit type conversion in Python.
This includes strings and Booleans supplied to integer fields.
Integral JSON numbers such as `32.0` remain valid where the schema permits integers.
The decision applies to the shared Go contract boundary.
Python and published schemas stay unchanged.
No implicit type conversion is enabled in Go.
