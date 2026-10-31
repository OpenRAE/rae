# Go cutover migration

Milestone 74 replaces the Python implementation of RAES with a Go
implementation in one cutover. The cutover removes the `raes` Python
distribution. The `python-distribution-go-cutover` record in
`specs/evolution/deprecation-records.yaml` is the deprecation notice.

## Versions

| Item | Version |
| --- | --- |
| First release that carries the notice | The first `raes` release after 10.2.0 |
| Removal eligibility | One release carries the notice |
| First release without the Python distribution | The release that contains the cutover |

## Surfaces that stay

The Go release keeps these surfaces and their machine-readable behavior:

- the RAES SDL and the published contracts in `contracts/schemas/`;
- the `raes` command: its commands, flags, exit codes, and JSON output;
- the `raes-mcp` server: its tools and their payloads;
- the control-plane HTTP API: its routes, payloads, and status codes.

Diagnostic codes and their locations stay the same. Help text and other free
text can change.

## Surfaces without a replacement

The Python import API has no replacement. This includes each module of the
`raes` and `raes_*` packages, for example `raes.parse_sdl_file`. Code that
imports these packages must use the `raes` command, the `raes-mcp` server, or
the HTTP API.

## Control-plane stores

The Go runtime does not read the control-plane stores that the Python runtime
wrote. A run in a store of the Python runtime does not continue under the Go
runtime.
