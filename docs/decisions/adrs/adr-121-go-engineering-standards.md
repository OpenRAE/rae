# ADR-121: Go Engineering Standards

## Status

accepted

## Date

2026-10-31

## Classification

Classification: FM0
Required artifacts: unit tests (the analyzers under `implementations/tooling/go/lint` and the command `implementations/tooling/go/cmd/regressiontest`), CI lanes (`.github/workflows/canonical-verification.yml` job `go`)
Waivers: none

The decision sets code standards and their checks. It adds no SDL, contract, or
runtime semantics.

## Context

Milestone 74 ports the codebase to Go and replaces the Python implementation in
one hard cutover. The Go code must follow the Google Go Style Guide to the
extent that a tool can check it deterministically. It must also pass strict
linting and mutation testing, and meet the repository standards that do not
depend on Python.

Google publishes its Go style guide as three documents. The
[Style Guide](https://google.github.io/styleguide/go/guide) and
[Style Decisions](https://google.github.io/styleguide/go/decisions) are
normative. [Best Practices](https://google.github.io/styleguide/go/best-practices)
is advisory.

These current standards are specific to Python:

- ruff;
- the ADR-015 cap on file length;
- the ADR-117 ratchets;
- Coverage.py under ADR-103;
- the ADR-116 exception classes;
- the nox graph of ADR-014.

ADR-106 admits the Go toolchain and the Go tool module (issue #1773 amendment).

## Decision

### 1. Scope

These standards apply to each Go module under `implementations/`. Today that is
the Go tool module `implementations/tooling/go`. Each new Go module joins the
CI matrix of the `go` job.

### 2. Formatting and strict linting

`gofmt` and `goimports` format all Go code. golangci-lint runs with
`implementations/.golangci.yml`, which enables all linters except a listed set.
Each disabled linter has a stated reason: it conflicts with Google Go style or
with a published contract, or an enabled check covers it. Any finding fails CI.

A `//nolint` directive must name the linter and state why the finding is false.
`nolintlint` checks the form. Review checks that the finding is false. An
exclusion in the configuration needs the same reason.

### 3. Google Go style

The [rule map](#appendix-google-go-style-rule-map) lists each rule of the three
documents. For each rule, it names the check that enforces the rule, or it
states why no deterministic check is possible. Such rules are review rules.

A published contract takes precedence over a style rule. For example, the
command and flag names of `raes` keep their published form.

### 4. Repository analyzers

Three `go/analysis` analyzers in `implementations/tooling/go/lint` check the
deterministic rules that no golangci-lint linter checks:

- `gotwant`: a test failure message prints the actual value before the wanted value.
- `getprefix`: a function or method name does not start with a Get prefix.
- `wrapverb`: `fmt.Errorf` places `%w` at the start or the end of the format.

`raesvet` combines them. CI runs `go vet -vettool=raesvet` on each module.

### 5. Contract-based development

The Go code uses these idiomatic forms of contract-based development:

1. The published schemas stay the authority. Go types for a published contract
   follow from its schema.
2. A type with invariants keeps its fields unexported. Its constructor checks
   the invariants and returns an error. Its methods rely on the invariants.
3. Input from outside the process is checked once, at the boundary where it
   enters. Validated types then carry it.
4. Interfaces are small, and their consumers define them. When an interface has
   more than one implementation, its owner provides an exported test suite that
   each implementation passes, as `testing/fstest.TestFS` does.
5. A function returns an error for bad input. It panics only when an internal
   invariant is broken.
6. Fuzz tests check the round trips and invariants of parsers and encoders.

### 6. Errors, logging, time, and randomness

- An error is the last result. Error strings start in lower case and have no
  final punctuation.
- A caller classifies a failure with `errors.Is` or `errors.As`. The six
  ADR-116 categories stay: invalid input, conflict, not found, authorization,
  operational, and evidence integrity.
- Code logs with `log/slog`. Library code never configures logging. Messages
  are constant, and records carry no input values.
- The behavior of ADR-116 that consumers see stays. The `raes` command exits
  with status 70 after an unexpected failure. An MCP tool result never contains
  the text of an unexpected error.
- Code reads the time from an injected clock (ADR-118), so `time.Now` is
  forbidden outside the clock owner. Randomness comes from `crypto/rand` or from
  the governed random streams, so `math/rand` is forbidden.

### 7. Tests

- Tests sit beside the code in `_test.go` files. They use the `testing` package,
  and `github.com/google/go-cmp` for comparisons. Assertion libraries are not
  allowed.
- CI runs the tests with the race detector.
- The statement coverage of each module is at least 90%, the ADR-103 floor.
- CI runs gremlins on the lines changed since the merge base with the base
  revision. Test efficacy and mutant coverage must each be above 90%. A change
  without mutants passes. Mutation testing runs in CI only.
- A regression test is a test function whose name starts with `TestRegression`.
  It must build and fail at the merge base. The `regressiontest` command checks
  each new regression test.
- Full test, mutation, and fuzz suites run in CI only. Local runs stay targeted.

### 8. Dependencies

Code uses the standard library first. The ADR-122 architecture model lists the
external import paths that each layer may import, each with a reason. The
golangci-lint `depguard` rule denies the standard library packages that section
6 replaces. ADR-106 governs how the module digests are admitted.

### 9. Standards that change and standards that stay

| Python standard | Go standard |
| --- | --- |
| ruff format and check | `gofmt`, `goimports`, golangci-lint, and the repository analyzers |
| ADR-015 cap on file length | No cap. `gocognit` limits complexity to 15, and ADR-122 governs structure. |
| ADR-117 ratchets | ADR-122 architecture model and the Go compiler rules |
| ADR-103 coverage with Coverage.py | 90% statement coverage of each Go module |
| ADR-116 exception classes | Section 6 |
| ADR-014 nox lanes | The `go` job of the canonical graph until issue #1801 |

These standards stay and apply to the Go code:

- the documentation style guide, Vale, and ASD-STE100 prose;
- ADRs and their pins;
- requirement traceability;
- contract governance under ADR-009 and ADR-061;
- pull request title and body guards;
- secret, vulnerability, and code scanning;
- artifact admission under ADR-106 and ADR-107;
- the SonarCloud quality gate;
- the assurance levels of ADR-007 and ADR-018.

## Alternatives Considered

- **go-mutesting for mutation testing.** It has no mode for changed lines.
  Gremlins has one.
- **A golangci-lint plugin for the repository analyzers.** A plugin needs a
  custom golangci-lint build. `go vet -vettool` is the standard Go mechanism.
- **Enable only a selected set of linters.** New linters would then stay off.
  Enabling all linters and disabling each one with a reason is stricter.
- **A cap on Go file length.** Google Go style sets no length limit. Complexity
  limits and the architecture model control structure.

## Consequences

- Each Go module meets the same checks from its first line of code.
- A style rule that a tool cannot check stays a review rule, and the rule map
  says so.
- Mutation testing and tool builds add CI time.

## Appendix: Google Go style rule map

"Review" means that no deterministic check is possible, because the rule needs
judgment about meaning or context.

### Style Guide

| Rule | Check |
| --- | --- |
| Style principles: clarity, simplicity, least mechanism, concision, maintainability, consistency | Review |
| Formatting | `gofmt` |
| MixedCaps | revive `var-naming`, staticcheck ST1003 |
| Line length | No limit; `lll` is disabled |
| Naming | revive `exported` (stutter); otherwise review |
| Local consistency | Review |

### Style Decisions

| Rule | Check |
| --- | --- |
| Underscores | revive `var-naming`, staticcheck ST1003 |
| Package names | revive `package-naming`, `var-naming` |
| Receiver names | revive `receiver-naming`, staticcheck ST1016 |
| Constant names | revive `var-naming` |
| Initialisms | revive `var-naming`, staticcheck ST1003 |
| Getters | `getprefix` |
| Variable names | Review |
| Repetition | revive `exported`; otherwise review |
| Comment line length | Review |
| Doc comments | revive `exported`, `godot` |
| Comment sentences | `godot` |
| Examples | `testableexamples` |
| Named result parameters | `nakedret`; otherwise review |
| Package comments | revive `package-comments`, staticcheck ST1000 |
| Import renaming | revive `redundant-import-alias`; otherwise review |
| Import grouping | `goimports` |
| Import "blank" | revive `blank-imports` |
| Import "dot" | revive `dot-imports`, staticcheck ST1001 |
| Returning errors | revive `error-return`, staticcheck ST1008 |
| Error strings | revive `error-strings`, staticcheck ST1005 |
| Handle errors | `errcheck` |
| In-band errors | Review |
| Indent error flow | revive `indent-error-flow`, `early-return`, `superfluous-else` |
| Literal formatting | `gofmt`, govet `composites` |
| Nil slices | Review |
| Indentation confusion | `gofmt`; otherwise review |
| Function formatting | `gofmt`; otherwise review |
| Conditionals and loops | `gofmt`; otherwise review |
| Copying | govet `copylocks` |
| Don't panic | `forcetypeassert`, `errcheck` type assertions; otherwise review |
| Must functions | Review |
| Goroutine lifetimes | govet `lostcancel`, `contextcheck`; otherwise review |
| Interfaces | `ireturn`, `iface`, `interfacebloat`; otherwise review |
| Generics | Review |
| Pass values | Review |
| Receiver type | `recvcheck` |
| switch and break | revive `unnecessary-stmt` |
| Synchronous functions | Review |
| Type aliases | Review |
| Use %q | gocritic `sprintfQuotedString` |
| Use any | revive `use-any`, `modernize` |
| Flags | Review; the published `raes` command contract takes precedence |
| Logging | `sloglint`, `depguard` denies `log`; otherwise review |
| Contexts | revive `context-as-argument`, `containedctx`, `contextcheck`, `noctx` |
| crypto/rand | gosec G404, `depguard` denies `math/rand` |
| Assertion libraries | `archcheck` ARCH-008 (ADR-122) |
| Identify the function | Review |
| Identify the input | Review |
| Got before want | `gotwant` |
| Full structure comparisons | Review |
| Compare stable results | Review |
| Keep going | Review |
| Equality comparison and diffs | `forbidigo` denies `reflect.DeepEqual`; otherwise review |
| Level of detail | Review |

### Best Practices

| Rule | Check |
| --- | --- |
| Function and method names: avoid repetition | revive `exported`; otherwise review |
| Naming conventions | `getprefix`; otherwise review |
| Test double and helper packages | Review |
| Shadowing | govet `shadow` |
| Util packages | revive `package-naming` |
| Package size | Review |
| Protocol Buffer messages and stubs | No protocol buffers are used |
| Import ordering | `goimports` |
| Error structure | `errorlint`, `errname`; otherwise review |
| Adding information to errors | Review |
| Placement of %w in errors | `wrapverb` |
| Logging errors | Review |
| Program initialization | `gochecknoinits`; otherwise review |
| Program checks and panics | Review |
| When to panic | Review |
| Documentation conventions: parameters, contexts, concurrency, cleanup, errors | Review |
| Preview | Review |
| Godoc formatting | `gofmt` |
| Signal boosting | Review |
| Variable initialization and zero values | revive `var-declaration`; otherwise review |
| Composite literals | Review |
| Size hints | Review |
| Channel direction | Review |
| Function argument lists: option structure, variadic options | Review |
| Complex command-line interfaces | Review |
| Leave testing to the Test function | Review |
| Designing extensible validation APIs and acceptance testing | Review; section 5 item 4 |
| Use real transports | Review |
| t.Error vs. t.Fatal | Review |
| Error handling in test helpers | `thelper` |
| Don't call t.Fatal from separate goroutines | govet `testinggoroutine` |
| Use field names in struct literals | govet `composites` |
| Keep setup code scoped to specific tests | Review |
| When to use a custom TestMain entrypoint | Review |
| Amortizing common test setup | Review |
| String concatenation | `perfsprint`; otherwise review |
| Constant strings | Review |
| Global state | `gochecknoglobals`; otherwise review |
| Interfaces: avoid unnecessary interfaces, ownership, design | `iface`, `interfacebloat`, `ireturn`; otherwise review |

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-10-31 | #1775 | Section 8 and the rule map: the ADR-122 architecture model lists the permitted external import paths. depguard keeps only its denials. Two lists use list format for ASD-STE100. |
