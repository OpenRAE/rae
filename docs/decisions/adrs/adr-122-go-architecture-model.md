# ADR-122: Go Architecture Model

## Status

accepted

## Date

2026-10-31

## Classification

Classification: FM0
Required artifacts: unit tests (`implementations/tooling/go/arch` and the command `implementations/tooling/go/cmd/archcheck`), CI lanes (`.github/workflows/canonical-verification.yml` job `go-architecture`)
Waivers: none

The decision sets the structure of the Go code and its checks. It adds no SDL,
contract, or runtime semantics.

## Context

Milestone 74 ports the codebase to Go. Issue #1775 requires one
machine-readable architecture model for the repository. Checks compiled from
the model must run on the whole repository, and each failure must state its fix.
Each change must also pass a check of its design against the model before code
exists.

ADR-036 gives each Python package one area. The Python packages do not keep
these boundaries: 703 import statements import 1,361 private names from other
modules. ADR-117 added ratchets with baselines for these problems. MOD-001
states its layering rules in Python terms.

The Go compiler enforces some structure. It rejects import cycles. It permits
an import of an `internal` package only from the tree of its parent directory.
Only exported identifiers are visible outside a package. The compiler does not
know layers, permitted dependencies, or the packages that a design declares.

## Decision

### 1. One model for the repository

`implementations/architecture.json` is the only architecture model, with the
schema `raes-go-architecture/v1`. All its directories are relative to the
repository root. The model declares these items:

| Item | Content |
| --- | --- |
| Module | The directory of a `go.mod` file and the module path that it states |
| Layer | A name, a directory, a description, the layers whose packages it may import (`uses`), and the permitted external import paths, each with a reason (`external`) |
| Package | A directory in its layer, a description, a `public` flag, and its first-party imports |

A package can import a package of its own layer. It can also import a public
package of a layer that its layer uses. The `uses` relation has no cycle. An
external path permits the import paths below it.

### 2. Layers

The layers follow the contract families and the areas of ADR-036 and ADR-115.
They do not copy the Python package structure.

| Layer | Directory | Uses | Content |
| --- | --- | --- | --- |
| `base` | `implementations/go/internal/base` | none | Shared primitives: canonical JSON, digests, random streams, input limits, errors, logging, and the clock |
| `contract` | `implementations/go/internal/contract` | `base` | Bindings and validation of the published contracts, concept authority, vocabularies, and profiles |
| `sdl` | `implementations/go/internal/sdl` | `contract`, `base` | Source loading, the document model, semantic validation, instantiation, and composition |
| `processor` | `implementations/go/internal/processor` | `sdl`, `contract`, `base` | Compilation, planning, trial compilation, and the analysis services |
| `backend` | `implementations/go/internal/backend` | `contract`, `base` | The interfaces that the runtime needs from a backend, backend manifests, and the backend test doubles |
| `runtime` | `implementations/go/internal/runtime` | `backend`, `processor`, `sdl`, `contract`, `base` | The control plane, its stores, distributed execution, and participant control |
| `conformance` | `implementations/go/internal/conformance` | `runtime`, `backend`, `processor`, `sdl`, `contract`, `base` | Processor and backend conformance checks |
| `app` | `implementations/go/internal/app` | `conformance`, `runtime`, `backend`, `processor`, `sdl`, `contract`, `base` | Services that the command line, the MCP server, and the HTTP API share |
| `adapter` | `implementations/go/internal/adapter` | `app`, `runtime`, `contract`, `base` | Thin adapters for the `raes` command, the `raes-mcp` server, and the control-plane HTTP API |
| `command` | `implementations/go/cmd` | `adapter`, `base` | The main packages of the `raes` and `raes-mcp` binaries |
| `parity` | `implementations/go/internal/parity` | none | The checker of the Go implementation against the golden corpus of the Python implementation (issue #1778) |
| `tooling` | `implementations/tooling/go` | none | Development tools: the repository analyzers, the architecture check, and CI checks |

The product layers are below `implementations/go/internal`. Thus the compiler
permits imports of them only from `implementations/go`. No layer uses
`parity` or `tooling`.

### 3. Rules and their checks

Each rule has exactly one check. `archcheck` is the command in
`implementations/tooling/go/cmd/archcheck`. `go build` is the Go compiler,
which each build and test runs.

| Rule | Statement | Check |
| --- | --- | --- |
| ARCH-001 | The model declares each Go module of the repository once, with the directory and the module path of its `go.mod`. | `archcheck` |
| ARCH-002 | Each layer has a unique name, a directory, and a description. It uses only other declared layers, and the uses have no cycle. | `archcheck` |
| ARCH-003 | Each package has a unique directory in its layer and in a declared module, and a description. | `archcheck` |
| ARCH-004 | Each import in the model names a declared package in the same layer, or a public package of a layer that the importer's layer uses. | `archcheck` |
| ARCH-005 | The model declares each Go package, and each declared package has code. | `archcheck` |
| ARCH-006 | The non-test files of each package import exactly the first-party packages that the model declares for it. | `archcheck` |
| ARCH-007 | The test files of each package import only first-party packages that ARCH-004 permits for it. | `archcheck` |
| ARCH-008 | Each external entry has a reason and is in use. A package imports an external path only when its layer lists it. | `archcheck` |
| ARCH-009 | This table states each rule that a check enforces, with that check. | `archcheck` |
| ARCH-010 | No packages import each other in a cycle. | `go build` |
| ARCH-011 | Only code in the tree of the parent of an `internal` directory imports the packages below it. | `go build` |
| ARCH-012 | Code outside a package uses only its exported identifiers. These identifiers are the public interface of the package. | `go build` |

An external path is an import path outside the standard library and the
declared modules. A standard library path has no dot in its first element.

### 4. The check command

`archcheck` runs from the repository root. It reads the model and checks the
rules that need only the model: ARCH-001 to ARCH-004 and the entries of
ARCH-008. With `-design`, it stops after these rules. Without `-design`, it also
checks the rule table of this ADR and the code. It loads each declared module
with `golang.org/x/tools/go/packages`, test files included.

Each finding names the rule and the location, and it states the change that
fixes it. For example:

```text
archcheck: ARCH-005 implementations/tooling/go/newtool: the model does not declare this package. Fix: declare the package, its layer, and its imports in the model through the design step.
```

The command exits with status 1 on a finding. The `go-architecture` job of the
canonical graph runs it, and the `gate` job requires that job.

### 5. The design step

Before a change writes Go code, it does these steps:

1. Declare each new or changed module, layer, package, import, and external
   entry in the model.
2. Name in the plan the exported identifiers that each new or changed package
   adds or changes.
3. Run `archcheck -design` on the changed model.

The change writes the code after the design check passes. In CI, `archcheck`
fails when the code and the model do not agree. Thus the model changes before
the code that needs the change. The plan rules in `.gc/plan-rules.md` require the
design check before implementation starts.

### 6. Dependencies

The model is the only list of permitted dependencies. ARCH-006 governs the
first-party imports, and ARCH-008 governs the external imports of each layer.
The golangci-lint `depguard` rule keeps only its denials of standard library
packages (ADR-121). ADR-106 governs the admission of module digests.

### 7. No baseline

The Go code starts with no findings. No check has a baseline or an allowlist.

## Alternatives Considered

- **go-arch-lint.** Version 1.19.1 checks the dependencies between components,
  the vendor packages of each component, and the files that no component
  matches. Its `self-inspect` command validates the configuration. Components
  match packages by directory globs, so a new package or a new import between
  permitted components changes no model. Thus a design cannot record them
  before the code. It also has no package visibility, and its messages state no
  fix.
- **depguard rules for each layer.** depguard denies imports by file glob. It
  does not classify packages, record package imports, or report unused
  permissions.
- **Bazel visibility rules.** Bazel would replace the go command, the module
  files, and the CI lanes for the whole repository.

## Consequences

- Each new Go package or import needs a model change. The change shows the
  design in review before the code.
- A package that the model does not classify fails CI.
- The model lists each external dependency with its reason. depguard no longer
  holds an allow list.
- `archcheck` is a small program on the standard Go package loader. The
  repository maintains it and its tests.

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-10-31 | #1778 | Section 2: the `parity` layer holds the checker of the Go implementation against the golden corpus. |
