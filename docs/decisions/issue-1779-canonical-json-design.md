# Canonical JSON and digests in Go

Issue #1779 ports the shared primitives to Go.
This part ports canonical JSON and the rendered SHA-256 digests.
[ADR-118](adrs/adr-118-shared-primitives-and-injected-wall-clock.md) records the shared primitives of the Python implementation.

## Problem

RAES digests use two canonical JSON forms.
Contract digests use RFC 8785, the JSON Canonicalization Scheme (JCS).
Schema content hashes and older digests use the text of Python `json.dumps` with sorted keys and compact separators.
The two forms differ, for example in number notation and in key order.
The Go forms must give the same bytes as the Python forms, because stored records hold the digests.

## Architecture

| Package | Function | Implementation |
| --- | --- | --- |
| `base/canonjson` | `JCS` | `github.com/gowebpki/jcs`, a maintained fork of the Go reference implementation by the author of RFC 8785 |
| `base/canonjson` | `Sorted` | A writer of the Python `json.dumps` text, with or without `ensure_ascii` |
| `base/digest` | `SHA256` | `crypto/sha256`, rendered as `sha256:` and 64 lowercase hexadecimal digits |

Both forms take UTF-8 JSON text with one value, and a later duplicate member replaces an earlier one, as in Python.
`JCS` refuses an integer above 2^53 - 1 in magnitude, because RFC 8785 gives it no exact value.
Both forms refuse a number outside the finite float64 range.
`Sorted` refuses an integer with more than 4,300 digits, as Python does (`sys.int_info.default_max_str_digits`).
It writes each other integer as its JSON text, which is the decimal form of Python, except `-0`, which Python reads as `0`.
Thus no form converts integer text to a big integer.

One difference from Python is deliberate.
The Python `ensure_ascii` form writes a lone UTF-16 surrogate back as a `\u` escape.
Both Go forms refuse it, because valid UTF-8 cannot hold it and I-JSON (RFC 7493) forbids it.
The Python RFC 8785 form and the Python form without `ensure_ascii` also refuse it.
Thus the corpus holds no lone surrogate.

`Sorted` is custom, because no Go encoder writes the Python text.
The standard library has an RFC 8785 canonicalizer, `Value.Canonicalize` in `encoding/json/jsontext`.
Go 1.27 builds that package only with `GOEXPERIMENT=jsonv2`, so `JCS` uses `gowebpki/jcs`.
`encoding/json` escapes U+2028 and U+2029, writes floats in another notation, and has no `ensure_ascii` mode.
`Sorted` writes each float as Python `repr` does: the shortest digits, and scientific notation below 1e-4 or from 1e16.

The parity corpus checks both forms.
Its `canonical` surface holds each JSON contract fixture and 32 edge texts.
The Go runner `canonical encode` compares the digest of each form with the Python result.

## Security and data flows

The protected asset is the integrity of the digests that identify contracts, schemas, and records.
The input text can come from outside the trust boundary, for example in a supplied contract payload.

```mermaid
flowchart LR
    Text[JSON text] --> Decode[Strict decode]
    Decode -->|refusal| Err[ErrInput]
    Decode --> JCS[JCS through gowebpki/jcs]
    Decode --> Sorted[Python json.dumps text]
    JCS --> Digest[SHA256 rendering]
    Sorted --> Digest
    Digest -->|sha256 and hex| Record[Contract, schema, or record digest]
```

| Threat | Control | Verification |
| --- | --- | --- |
| Two different texts get one encoding, so one digest names two values | The decoder refuses invalid UTF-8, a lone surrogate escape, and data after the value. `encoding/json` would replace a lone surrogate. | `TestFormsRefuseInputWithoutAnEncoding` |
| A large integer loses precision and changes a JCS digest | `JCS` refuses an integer above 2^53 - 1 in magnitude | `TestJCSRefusesAnInexactInteger` |
| A digest differs between the Python and the Go implementation | The corpus compares each form for each fixture and edge text | `TestCorpus` and `TestFormsMatchThePythonReference` |
| A non-finite number gets an encoding | Both forms refuse a number outside the finite float64 range | `TestFormsRefuseInputWithoutAnEncoding` |
| A long integer costs quadratic time in a big-integer conversion | `JCS` reads an integer only within the int64 range, and `Sorted` copies the integer text and refuses more than 4,300 digits | `TestJCSRefusesAnInexactInteger` and `TestSortedKeepsThePythonIntegerDigitLimit` |
| Deep nesting exhausts the stack | `encoding/json` refuses nesting above 10,000 levels | The Go standard library |
| A form is not stable under repeated encoding | Each `Sorted` text encodes to itself, and each JCS text is canonical for the transform | `FuzzForms` in CI |

## Supporting artifacts

- `implementations/go/internal/base/canonjson/` and `implementations/go/internal/base/digest/`
- The `canonical` surface of `tools/parity_corpus.py`
- [Golden parity corpus design](issue-1778-parity-corpus-design.md)

## References and document review

- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)
- [github.com/gowebpki/jcs](https://github.com/gowebpki/jcs)
- Issue #1779
