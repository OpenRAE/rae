# ADR-116: Shared Exceptions and Operational Logging

## Status

accepted

## Date

2026-10-28

## Classification

Classification: FM0
Required artifacts: ADR, unit tests (hierarchy, value-free log records, application logging configuration and each failure boundary)
Waivers: none

This decision changes how failures are typed, reported and logged.
It adds no semantic, graph or stateful reasoning.
Each refusal keeps its condition, its state effect and its status at each surface.

## Context

Issue #1678 found no shared logging utility and no shared exception root.
`SDLError` covered only SDL parsing, validation and instantiation.
In the packages, 34 other exception classes derived directly from `Exception`, `ValueError` or `RuntimeError`.
No entry point configured logging, and five package modules logged.

The runtime used built-in exceptions as domain signals.
`PermissionError` meant a refused authority, `KeyError` meant an absent operation, and `ValueError` meant a conflict.
`TimeoutError` and `RuntimeError` meant an unavailable runtime.
The HTTP routes caught these built-in exceptions around complete runtime calls.
Thus a programming error that raised `ValueError` became a 409 response, without a log record.
OWASP requires a generic response and a server-side record for an unexpected error.

Ruff rule `BLE001` found 112 broad handlers that neither raised again nor logged.
FastMCP puts the text of an unexpected tool exception in the tool result.
Typer prints a Rich traceback that includes exception messages.
Pydantic validation errors include input values in their text.
Thus exception text and tracebacks can disclose values that the surfaces otherwise redact.

[ADR-075](adr-075-ecosystem-versioning-deprecation-and-migration-governance.md) states that its versioning policy creates no cross-package exception hierarchy.
This decision creates that hierarchy for the Python code.
The issue #1678 architecture preflight records the binding guardrails.

## Decision

### 1. One exception root with categories

`raes_contracts.errors` defines `RaesError` and six categories.
The categories follow the distinctions that callers need, as PEP 8 recommends:

- `InvalidInputError`: input from outside the program does not satisfy a governed contract.
- `ConflictError`: the request conflicts with the current governed state.
- `NotFoundError`: a named governed object does not exist for the caller.
- `AuthorizationError`: the caller does not have authority for the operation.
- `OperationalError`: a dependency, a tool, a host resource or a time budget failed.
- `EvidenceIntegrityError`: evidence does not replay against, or does not match, its governed input.

`raes_contracts` is the neutral package that every first-party package can import under ADR-036.
The module uses only the standard library and Python 3.12 syntax.
Thus the bootstrap tools can import it from the source tree.

### 2. Single inheritance

Every exception class in the repository derives from `RaesError` through one base class.
No class combines a RAES base with a built-in or third-party exception base.
The Python documentation recommends this, because exception bases can conflict in `args` handling and memory layout.

Existing families keep their names, import paths, constructor arguments and attributes.
`SDLError` and `ExperimentSpecError` derive from `InvalidInputError`.
`ScenarioError` derives from `RaesError`, because its members have different categories.
Classes that derived from `ValueError` or `RuntimeError` now derive from a category.
This is a breaking change for code that caught them as built-in exceptions.

### 3. Built-in exceptions for programming errors and protocols

Built-in exceptions remain for programming errors, such as a wrong argument type.
Pydantic validators raise `ValueError` or `PydanticCustomError`, because Pydantic converts only these into a `ValidationError`.
Protocols keep the exceptions that they require, such as `KeyError` in `__getitem__`.

### 4. Domain failures use the categories

Code raises a category for each failure that correct code can reach because of input, state or the environment.
The runtime raises `AuthorizationError`, `NotFoundError`, `ConflictError` and `OperationalError` in place of the built-in signals.
The HTTP routes map these categories to the existing statuses and details.
A built-in exception from a programming error reaches the existing 500 handler.

### 5. Standard library logging with value-free records

RAES uses the standard `logging` package.
Library code gets loggers through `get_logger(__name__)` and never configures logging.
`get_logger()` adds a filter that makes each first-party record value-free before a handler gets it.
The filter replaces exception information with exception types and frame locations.
It escapes control characters in the message.

RAES applications configure logging at their entry point.
These applications are the `raes` command, the `raes-mcp` server and the repository tools.
`run_application()` configures one standard error handler with `ValueFreeFormatter`.
It logs an unexpected failure one time and returns the unexpected-failure status of the application.
The `raes` command uses status 70, which its command contract already documents.
A host that embeds RAES owns its logging configuration.

The type names and frames of code that RAES does not own are foreign content.
Examples are a backend, a provider and an installed resolver.
An isolation handler for that code logs `foreign_failure_record()` one time, and the record keeps only the RAES frames.

### 6. Boundaries handle failures one time

Each surface has one boundary for unexpected failures.
A broad handler is a boundary, a cleanup that raises again, or an isolation of foreign code that logs.
[`docs/develop/exceptions-and-logging.md`](../../develop/exceptions-and-logging.md) is the maintained policy.

### 7. Ruff enforces the mechanical rules

The Ruff configuration selects `BLE`, `LOG`, `G`, `TID251` and the `TRY` rules that agree with this policy.
`TID251` bans direct logging configuration outside `raes_contracts.operational_logging`.
Tests check the hierarchy, the value-free records and each boundary.

## Alternatives Considered

Bridge classes that combine `RaesError` with `ValueError` or `RuntimeError`.
Rejected: the Python documentation recommends one exception base.
Bridges also keep the broad built-in catches that report programming errors as domain failures.

Translation at the HTTP boundary only.
Rejected: a route cannot tell a programming error from a domain failure when both are `ValueError`.

A third-party logging framework.
Rejected: it adds a dependency, and a library must not impose a logging framework on its host.

A formatter that removes secrets with patterns.
Rejected: patterns cannot remove secrets from arbitrary object representations or exception chains.

The exception root in the `raes` package.
Rejected: ADR-036 does not let every package import `raes`.

## Consequences

Callers can catch all RAES failures with one class.
They can also tell input, conflict, absence, authority, operational and evidence failures apart.
A programming error in a runtime call becomes a 500 response and a server log record, not a conflict.
First-party log records and RAES application output contain no exception values.

Code that caught re-parented classes or runtime refusals as built-in exceptions must catch the new classes.
The release that contains this decision is a major release.
The bootstrap tools add the source path for `raes_contracts`.
The two shared modules must keep Python 3.12 syntax.

Starlette raises an unexpected exception again after the 500 response, so the ASGI server logs it.
The host must format server logs with `ValueFreeFormatter` to keep these records value-free.
This residual risk is outside the control of RAES.
