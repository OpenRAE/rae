# Semantic command results

This reference describes the Python semantic CLI in RAES 11.0.2.
For a task procedure, use [check an artifact](guides/cli.md).

## Contracts and output

Each command accepts a path or `-` for stdin.
SDL uses `sdl-yaml/v1` by default. Portable JSON needs its published contract ID.
Human and JSON output use the same typed result.
JSON mode writes one document and a newline to stdout.
The result records the source format, contract, and applicable operation profiles.

The exit statuses are stable for automation:

| Exit | Meaning |
| ---: | --- |
| `0` | The selected operation completed successfully. |
| `1` | Authored or portable input was rejected. |
| `2` | A command, option, or selector was invalid. |
| `3` | The selected operation is not supported for that contract or profile. |
| `4` | A bounded input/output or other expected operational failure occurred. |
| `70` | An unexpected failure was sanitized at the CLI boundary. |

Semantic commands do not fetch remote modules or search pack layouts. They do
not write lockfiles or caches. They do not publish data, call backends, or
manage experiments. `resolve` reads the RAES declarations and references in an
accepted scenario. env-packs owns module fetch and lockfile workflows.

Operations are available only when the selected contract has an owning semantic
API. SDL supports parse, validate, normalize, resolve, compile, transform, and
inspect. Portable JSON contracts support validate, inspect, and conformance.
Other combinations return exit `3`; in particular, the CLI does not describe
portable contract admission as parse-only behavior or SDL validation as a
conformance report.

## Existing compatibility surfaces

Use `raes sdl format --check` to check the source format. The old `raes sdl
resolve`, `verify-imports`, and `publish` commands maintain module packages.
`sdl resolve` writes a lockfile. `verify-imports` checks locked imports.
`publish` writes an OCI layout. Publication resolves relative and symlinked
entrypoints to one canonical module root and produces deterministic tar+gzip
bytes: identical module bytes produce identical bundle and manifest digests.
The completed layout replaces an older layout transactionally, so stale blobs
or files are not retained and a failed commit preserves the prior layout.

Signing is explicit. Pass `--signer-id` and `--private-key` together to produce
an Ed25519 signature, or omit both for unsigned publication. Supplying only one,
an unreadable/invalid key, or a signer id with surrounding whitespace fails
closed rather than silently publishing unsigned content.

These commands are not part of the offline `raes semantic` contract. Pack-aware
workflows belong in env-packs. OCI resolution uses bounded configured timeouts;
its digest-bound extraction cache is committed only after complete validation,
and malformed registry JSON is reported as a stable `SDLParseError` without
including response bodies or decoder internals.

Use `raes processor --help` and `raes conformance --help` for the processor and
backend-contract surfaces.
`raes conformance processor` runs finite compilation and planning checks.
`raes conformance backend --profile provisioning-only` checks the published fixtures.
Both commands accept `--format text`; JSON remains the default.
The report separates requested scope, achieved scope, support gaps, and evidence limits.
Fixture success proves no native backend execution.
The [CLI API reference](api/cli.rst) lists the
current command implementation.

Read [artifact concepts](concepts.md) for the boundary between accepted structure and realized behavior.
