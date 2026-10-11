# Work with RAES artifacts from the command line

Use `raes semantic` to work with RAES data. It provides `parse`, `validate`,
`normalize`, `resolve`, `compile`, `transform`, `inspect`, and `conformance`
commands. Each command accepts a file path or `-` for stdin. Each command is
offline and read-only by default.

Each command reads one document as in-memory text, so it does not expand SDL
`imports`. A scenario with top-level `imports` is rejected with exit `1` and
only the generic `sdl.parse` diagnostic, even when the composed scenario is
valid. To check such a scenario, parse its file with `parse_sdl_file` in
Python, as the [Python guide](python.md) shows.

From a repository checkout:

```console
uv run --project implementations/python raes semantic --help
```

Each run names a versioned input contract. SDL uses `sdl-yaml/v1` by default.
For portable JSON, pass its published contract ID.

```console
uv run --project implementations/python raes semantic parse scenario.sdl.yaml \
  --contract sdl-yaml/v1 --output json
uv run --project implementations/python raes semantic validate - \
  --contract operation-status-v1 --output json < operation-status.json
uv run --project implementations/python raes semantic normalize scenario.sdl.yaml \
  --contract sdl-yaml/v1 --migration-policy reject
uv run --project implementations/python raes semantic compile scenario.sdl.yaml \
  --contract sdl-yaml/v1 --output json
uv run --project implementations/python raes semantic transform scenario.sdl.yaml \
  --contract sdl-yaml/v1 --transform canonical --output json
```

Human and JSON output use the same typed result. JSON mode writes one stable
JSON document and a newline to stdout. Each result records the contract and
source format that were used. It also records the migration, normalization,
validation, processor, and transform profiles that apply. Pretty JSON is a
stable CLI format. Only the `canonical` transform emits RFC 8785 SDL bytes.

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
backend-contract surfaces. The [CLI API reference](../api/cli.rst) documents the
main `raes` command and its `semantic`, `sdl`, `processor`, `conformance`,
`libvirt`, `corpus`, and `runtime` groups. Run `raes --help` to list the
groups of your installed version.
