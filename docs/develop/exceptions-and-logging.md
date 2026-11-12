# Exceptions and operational logging

This page is the policy for exceptions and operational logs in all Python code in this repository.
[ADR-116](../decisions/adrs/adr-116-shared-exceptions-and-operational-logging.md) records the decision.
The shared code is in two modules:

- `raes_contracts.errors` defines the exception hierarchy.
- `raes_contracts.operational_logging` defines the logging utilities.

Both modules use only the Python standard library.
They keep Python 3.12 syntax, because the development container bootstrap imports them with Python 3.12.

## Scope

The policy applies to this source:

- the packages in `implementations/python/packages/`;
- the tests and test doubles in `implementations/python/tests/`;
- `tools/`, `noxfile.py`, `implementations/tooling/` and `implementations/formal/`;
- the build hook and the research scripts in `implementations/python/`;
- the research scripts in `docs/research/` and the Sphinx configuration in `docs/public/`.

The scripts in `docs/research/execution-architecture/experiments/` are recorded research evidence.
The experiment report binds each of them by a SHA-256 digest, so this policy does not change them.
Research captures and generated files are records, not source.

## Exception hierarchy

Every exception class that this repository defines derives from `RaesError`.
Each class has one base class.
Do not combine a RAES class with a built-in or third-party exception class.
Python recommends one exception base, because two exception bases can conflict.

| Class | Meaning | Usual handling |
| --- | --- | --- |
| `RaesError` | Root of all RAES exceptions | Catch it only at a boundary |
| `InvalidInputError` | Input from outside the program does not satisfy a governed contract | Tell the caller what to correct |
| `ConflictError` | The request conflicts with the current governed state | Refuse; the caller can try again after the state changes |
| `NotFoundError` | A named governed object does not exist for the caller | Tell the caller that the object is absent |
| `AuthorizationError` | The caller does not have authority for the operation | Refuse without detail |
| `OperationalError` | A dependency, a tool, a host resource or a time budget failed | Report the failure; a later attempt can succeed |
| `EvidenceIntegrityError` | Evidence does not replay against, or does not match, its governed input | Reject the evidence |

A family class groups the errors of one subsystem, for example `SDLError`.
Put a family under the category that applies to all of its members.
Put a family directly under `RaesError` when its members have different categories.
Public classes keep their names, import paths, constructor arguments and attributes.
A private exception that controls the flow of one module also derives from `RaesError`.

Tests can define exceptions that simulate a foreign failure, an interruption or test control flow.
These test doubles do not derive from `RaesError`.

## Raise

**E1.** Raise a `RaesError` subclass for a domain failure.
Correct code can reach a domain failure because of input, stored state or the environment.
The caller is expected to handle it.

**E2.** Raise a built-in exception for a programming error.
Use `TypeError` when code gives an object of the wrong type.
Use `ValueError` when code gives an argument value that the contract of the function does not permit.
Use `RuntimeError` for an internal invariant that only a defect can break.
Use `assert` only to state a condition that earlier code guarantees.

**E3.** Validation of a value object raises `ValueError`.
This applies to Pydantic validators, to `__init__` and `__post_init__` checks, and to each function that checks the fields of the object.
It also applies when other code calls such a function.
Pydantic changes only `ValueError`, `AssertionError` and `PydanticCustomError` into a `ValidationError`.
Thus a validator must not let a `RaesError` subclass or a `TypeError` escape.
A validator that calls a function that raises a `RaesError` subclass catches it and raises `ValueError` from it.

**E4.** Raise the exception that a protocol requires.
Examples are `KeyError` in `__getitem__`, `AttributeError` in `__getattr__` and `NotImplementedError` in an abstract method.
Other examples are `typer.BadParameter` for a bad command option and `HTTPException` in a FastAPI route.

**E5.** Do not raise `Exception` or `BaseException`.
Do not use `assert` to check input, because Python removes `assert` statements under `-O`.

**E6.** When you replace an exception, chain it: `raise NewError(...) from exc`.
Use `from None` only to keep the values of the cause out of the output.
Then give the new exception the safe details that the caller needs.
To raise the same exception again, use a bare `raise`.

**E7.** Write messages without values that the surface must not show.
Do not put secrets, credentials, tokens, raw request content or authored content in a message.
Do not put the text of a different exception in a message.
Identifiers that the surface already shows are permitted.
Put data that a handler needs in attributes, for example `SDLParseError.diagnostics`.
Two cases can give the text of a different exception:

- A diagnostic for the author of a document can give the error text of a parser, decoder or schema validator for that document.
  The author already has the document.
- The output of a repository tool can give the error text of a parser, decoder, validator, subprocess, network client or the operating system.
  The developer who runs the tool controls the repository content and the tool environment.
  Do not put secrets, credentials or tokens in that output.

**E8.** Return a `Diagnostic` for an expected finding that the caller reports, for example a validation finding.
Raise an exception when the operation cannot produce its result.

**E9.** Change an exception into a category at the boundary that owns the meaning.
For example, a runtime admission that calls a value validation catches `ValueError` around that one call.
Then it raises `ConflictError` from it.
Do not wrap the same failure again at each layer.

## Handle

**H1.** Catch only the exceptions that the code expects.
Put in the `try` block only the statements that can raise them.

**H2.** Catch `Exception` or `BaseException` only in one of these forms:

- **Boundary.** The outermost handler of a request, a command, a tool call, a task or a worker loop. It writes the error output of the surface. It logs the failure one time.
- **Cleanup.** The handler releases resources or rolls back changes, then uses a bare `raise`. Use `finally` or a context manager where possible. Use `BaseException` only in this form.
- **Isolation.** The handler contains a failure of code that RAES does not own. Examples are a backend, a provider, a participant runtime, and a resolver or callback that a host installs. It logs `foreign_failure_record(exc)` one time, at that boundary. Then it changes the failure into a typed outcome or into a `RaesError`. The record keeps the RAES frames, and it omits the type, message, chain and frames of the foreign code.

**H3.** Do not suppress an exception silently.
A handler that continues after an unexpected failure logs that failure.
An expected outcome, such as an absent optional file, does not need a log record.

**H4.** Do not change or suppress `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit` or `GeneratorExit`.
A cleanup handler can catch them, but it must raise them again.
Where an `ExceptionGroup` can occur, keep its members and use `except*`.

**H5.** Do not catch a broad built-in exception, such as `ValueError` or `KeyError`, to find a domain failure.
Catch the `RaesError` subclass.
A broad built-in catch also catches programming errors and reports them as domain failures.

## Log

**L1.** In library code, get the logger with `get_logger(__name__)` from `raes_contracts.operational_logging`.
Library code does not configure logging.
It does not add handlers, set levels, call `logging.basicConfig()` or log to the root logger.

**L2.** A RAES application configures logging one time, at its entry point.
It calls `configure_application_logging()` or runs inside `run_application()`.
A command option that selects the level calls `set_application_log_level()`, which adds no handler.
The RAES applications are the `raes` command, the `raes-mcp` server and the repository tools.
A host that embeds RAES owns its logging configuration.
Examples of hosts are an ASGI server and a Temporal worker process.

**L3.** Log a failure one time, at the boundary that handles it.
Do not log an exception and then raise the same exception again.
Exception: when `raise ... from None` hides an unexpected cause, log the cause first.

**L4.** In a handler, use `logger.exception()` for an unexpected failure.
Use `logger.warning()` for a handled condition that is not normal, for example a degraded operation.
Use `logger.info()` for normal lifecycle events and `logger.debug()` for diagnostic detail.
Use `logger.critical()` only when the process cannot continue.

**L5.** Use a constant message with `%s` arguments, for example `logger.warning("lease expired for %s", run_scope)`.
Do not format the message yourself.
Use only bounded arguments without secrets: event names, counts, type names and identifiers that the surface already shows.

**L6.** Never log secrets, tokens, credentials or connection strings.
Never log raw payloads, authored scenario content, environment maps, command lines or the output of a child process.

**L7.** Logs are not command output.
A command writes its results and its errors for the user with `print()` or `typer.echo()`.
Log records go to standard error.
An output stream that carries a protocol, such as command JSON or MCP stdio, carries no log records.

**L8.** Use `warnings.warn()` only for a condition that the calling code can remove, such as use of a deprecated function.
Use `logger.warning()` for a condition that the caller cannot change.

**L9.** Temporal workflow code logs with `temporalio.workflow.logger`, which suppresses records during replay.
Sphinx extensions log with `sphinx.util.logging`, which Sphinx needs for its warning handling.

**L10.** Operational logs are not evidence, audit records or participant observations ([ADR-066](../decisions/adrs/adr-066-observability-evidence-plane-separation.md)).

## Value-free records

`get_logger()` adds one filter to the logger.
The filter changes each record before a handler gets it:

- It replaces the exception information with a value-free traceback. The traceback keeps the exception types and the file, line and function of each frame. It omits exception messages, notes, source lines and local variables.
- It removes stack information.
- It merges the arguments into the message and escapes control characters. This prevents log injection.

Thus a host formatter cannot show values from an exception.
`ValueFreeFormatter` applies the same rules to records from other libraries.
`configure_application_logging()` installs it on one standard error handler.
`describe_exception()` gives the same description on one line.
The type names of code that RAES does not own are foreign content, so isolation handlers log `foreign_failure_record()` for them.

## Boundaries

| Surface | Domain failure | Unexpected failure |
| --- | --- | --- |
| `raes` command | The command writes a message to standard error and exits with its documented status. A bad option raises `typer.BadParameter`, which exits with status 2. | `run_application()` writes a value-free log record and exits with status 70. |
| `raes-mcp` server | The tool returns its existing error result. | The tool logs a value-free record and raises a `ToolError` with a fixed message. |
| Control-plane HTTP API | Routes map `AuthorizationError` to 403, `NotFoundError` to 404 and `OperationalError` to 503. Other `RaesError` subclasses get the existing 409 conflict response. A route keeps a different status that it already documents for a refusal. | The 500 handler returns a fixed response. Starlette raises the exception again for the ASGI server, so the host formats server logs with `ValueFreeFormatter`. |
| Conformance runner | The check records a diagnostic with a sanitized message. | The check records a diagnostic with a sanitized message. |
| Temporal activity | The activity raises a value-free exception, and Temporal records the failure. | The activity logs the cause, then raises a value-free exception. |
| Repository tool | `main()` writes a message to standard error and returns a status that is not zero. | `run_application()` writes a value-free log record and exits with status 1. |

## Enforcement

Ruff applies these rules in CI:

| Ruff rules | Policy rules |
| --- | --- |
| `BLE001`, `S110`, `S112` | H2, H3 |
| `B904`, `TRY201` | E6 |
| `TRY002` | E5 |
| `TRY203`, `TRY300` | H1 |
| `TRY400`, `TRY401`, `LOG` | L4 |
| `G` | L5 |
| `TID251` | L1, L2 |

Tests check the hierarchy, the value-free records, the application configuration and each boundary.

## Sources

- [Python Logging HOWTO](https://docs.python.org/3.14/howto/logging.html): when to use logging, logger names and library configuration.
- [Python logging cookbook](https://docs.python.org/3.14/howto/logging-cookbook.html): patterns to avoid and contextual information.
- [Python logging configuration](https://docs.python.org/3.14/library/logging.config.html): security considerations.
- [Python built-in exceptions](https://docs.python.org/3.14/library/exceptions.html): exception context and inheritance from built-in exceptions.
- [Python tutorial: errors and exceptions](https://docs.python.org/3.14/tutorial/errors.html): user-defined exceptions, chaining and notes.
- [PEP 8](https://peps.python.org/pep-0008/): programming recommendations for exceptions.
- [Pydantic validators](https://pydantic.dev/docs/validation/latest/concepts/validators/): exceptions that a validator raises.
- [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/): exception handlers.
- [Typer exceptions](https://typer.tiangolo.com/tutorial/exceptions/): Rich tracebacks and local values.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): tool execution errors.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude and log injection.
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): generic responses and server-side details.
