# Issue 1678: Shared exceptions and logging preflight

Date: 2026-10-28

Contract: issue #1678, supplied title, outcome and acceptance criteria; no
Ground Control requirement. This is non-normative architecture guidance, not
an implementation plan or the completed logging policy. No source behavior is
changed. The issue still requires the complete migration in one pull request.

## Decisions and ownership

- Use Python's standard `logging`, with small shared utilities rather than a
  logging framework. Put the shared exception root and dependency-light logging
  utilities in public modules of `raes_contracts`, the incumbent neutral package
  allowed by every first-party package's import rules. Keep these modules
  standard-library-only and free of import-time application configuration,
  model loading, I/O and imports of SDL, runtime or processor implementations.
  `raes_contracts/__init__.py` is currently inert; preserve that property.
- One hierarchy means one root for project-owned domain failures, derived from
  `Exception`, with existing domain families underneath it. It does not mean
  replacing Python's or dependencies' exceptions, framework control signals,
  or every `raise ValueError` with a project error. One policy must explicitly
  cover those cases too. Keep branches tied to actual caller handling needs,
  not one class per module, transport status or logging level.
- Preserve the identity, import paths, constructor arguments and diagnostic
  attributes of existing public exceptions through their owning modules.
  `SDLError` remains SDL-specific, not the root for unrelated failures.
  Preserve builtin catch compatibility where callers rely on it. A shared
  `ValueError`-compatible branch may require a narrow inheritance bridge to
  the project root; justify and test it rather than proliferating diamonds.
  Python recommends single inheritance: never combine unrelated builtin
  exception layouts or reparent dependencies' classes.
- Keep validator `ValueError`/`PydanticCustomError` behavior and aggregated
  Pydantic `ValidationError`. A generic project exception in a validator can
  bypass aggregation; `TypeError` in Pydantic v2 is a programming error, not a
  validation result. Translate only at an owned boundary where the caller
  needs a domain failure. Avoid repeated wrapping at every call layer.
- Application entry points own explicit, repeatable logging configuration.
  Libraries acquire named loggers and may attach `NullHandler`; they must not
  install output handlers or configure the root logger. Preserve host handlers
  and third-party loggers; no `basicConfig(force=True)` or blanket disabling.
  The issue's final policy should have one maintained home under
  `docs/develop/`, with API docs and entry-point help referring to it.

## Incumbents and repository scope

Paths below are relative to `implementations/python/packages/` unless noted.

| Concern | Canonical incumbents to build on |
| --- | --- |
| Module ownership and packaging | ADR-015, ADR-036, `tools/policy/adr_policy.yaml`, `tools/policy/repo_policy.py`; wheel package list and Python 3.14 support in `implementations/python/pyproject.toml` |
| Existing exception families | `raes/_errors.py`, `raes/scenarios.py`, `raes_contracts/experiment_spec.py`; processor satisfiability, exploit-path, participant-opacity and reconciliation errors; backend manifest errors; runtime revision/claim/mutation errors; `tools/policy/requirement_governance.py` and release-evidence/tool-acquisition errors |
| Diagnostics and results | `raes_contracts/diagnostics.py`: `Diagnostic`, `DiagnosticModel`, `portable_diagnostic_payload`; `raes/_model_diagnostics.py`, `raes/_language_diagnostics.py`, `raes_runtime/diagnostics.py`, `raes_runtime/backend_result_diagnostics.py`; `raes_conformance/conformance/diagnostics.py::sanitized_failure_message` |
| Validation and ingress | `raes/parser.py`, `raes/validator/`, `raes/_base.py`, `raes_contracts/json_ingress.py`, `_domain_profile_validation.py`, `admitted_trial_plan_ingress.py`; published schemas and generated parity, not a new validation registry |
| Transport and admission | `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `_operation_routes.py`, `_responses.py`, `control_plane_api_guards.py`, `control_plane_api_models.py`; `raes_mcp/server.py` and existing tool result builders; `raes_cli/entrypoint.py` and command handlers |
| Secrets and environment | ADR-056/057; `raes/runtime_values.py::enforce_observed_value_redaction`, `raes/runtime_environment.py`, `raes_contracts/secret_references.py`, `experiment_bindings.py`, and `raes_processor/trial_compiler/bindings.py` |
| State, audit and execution | ADR-104/113; `raes_runtime/control_plane_store*`, especially local transaction/codec and PostgreSQL owners; `control_plane_recovery.py`, `operation_temporal_workflow.py`, `operation_temporal_worker.py`; `raes_operations/run_artifacts.py` |
| Operational logs already present | `raes/scenarios.py`, `raes_contracts/experiment_spec.py`, runtime API/auth/guard modules, `tools/public_docs_guard.py`, the scoped `filelock` logger setting in `tools/verified_tool_installation.py`, and Temporal's `workflow.logger` |

The review surface is the whole current repository: all first-party packages,
tests and support doubles, root `tools/`, `implementations/tooling/`, `noxfile.py`
and `tools/nox_support/`, `.github/workflows/`, hooks, `.devcontainer/`, executable
examples and documentation scripts. Check entry points and dependency-generated
output as well as explicit logger calls: Rich/Typer output, warnings, uncaught
exceptions, subprocess stderr and ASGI/MCP/Temporal diagnostics can expose data.
Python policy does not require rewriting shell or formal-language errors into
Python classes. Their failure/output boundaries must follow the same policy.
Do not rewrite immutable research captures or generated artifacts as source.

Standalone tooling is a bootstrap constraint: the frozen tooling environment
does not install the application distribution. Reuse the fixed repo-local
source-path setup in `tools/check_generated_schemas.py` where a source import is
needed; do not copy a second hierarchy into `tools/`, depend on an editable
application install, scan for another checkout, or add a path from user input.
Prove shared imports work both in that environment and in the installed wheel.

## Security and contract gates

| Layer the design crosses | Required behavior |
| --- | --- |
| Parse and shape validation | Preserve safe YAML loading, duplicate-key/strict JSON rejection, variable and reference rules, closed Pydantic models and schema parity. Validators remain the source of admission decisions; logging must not repeat or weaken validation. |
| Configuration and environment bindings | Preserve `ControlPlaneConfiguration` and `ControlPlaneSecurityConfig` shape checks and immutable admitted authority. Logging options belong to trusted application setup, not SDL/runtime inventory or arbitrary request payloads. Use bounded choices for level/format. Never accept user-provided `dictConfig` factories, import strings or a configuration listener. Preserve literal-versus-`value_from` exclusion, secret-reference-only secret bindings and operator-secret restrictions. |
| Authentication and authorization | Preserve route authority inventory, principal/target/audience checks, application composition seal and admission-before-422 behavior. Correlation fields are metadata, never authority. Do not log bearer tokens, proxy credentials, arbitrary headers, rejected principal contents or sensitive URL query strings. Do not add a second auth or request middleware chain for logging. |
| Secret and information-flow controls | Reuse explicit raw-value omission and secret-reference contracts. Secret-name heuristics are advisory, not a disclosure guarantee. A `secret_fixture` value being permitted in SDL does not authorize publishing it in operational logs. Hidden participant/control assets and foreign tenant data must remain absent from logs. |
| Error envelopes and diagnostic schemas | Keep stable redacted 4xx/5xx details, conflict distinctions, no-store headers and existing CLI/MCP/result envelopes. `DiagnosticModel` already bounds codes, domains, JSON pointers and messages (512 characters); do not replace it with serialized exception objects. SDL source ranges and aggregated errors remain intact. Bound and escape untrusted fields; even a syntactically valid path or extra-field name can contain a secret. |
| Runtime/host output | Safe exception text alone is insufficient: `exc_info`, chained exceptions, exception notes/groups, Rich locals, server debug pages, Uvicorn access/error logs and worker failure serialization can disclose raw data. Review actual entry-point/framework output, including errors re-raised after a safe response. Default diagnostics must be value-free; debugging verbosity never relaxes disclosure rules. |
| Process and OS exposure | Preserve argument-list subprocess invocation and existing secret delivery channels. Never put credentials in argv, shell interpolation or shell tracing. Do not log environment maps, command lines, connection DSNs, `CalledProcessError` output or raw child stdout/stderr. Keep operational logs on stderr; reserve CLI JSON/stdout and MCP stdio stdout for their protocols. No automatic files, sockets, collectors or new external services. |
| Persistence, audit and failure recovery | Reuse store transactions, rollback/re-raise paths, revision conflicts, idempotency reservations and protected run archives. Logging failure must not change an already-selected response or conceal a failed mutation. Mandatory audit persistence keeps its existing admission semantics; a log line is not an audit receipt. Secondary rejection-audit failure keeps the bounded-label behavior already in API guards. Do not persist exception instances, traceback objects or secrets in state/history. |

`sanitized_failure_message` is useful existing work, not a universal safe
renderer: it is conformance-owned and names exception classes. API errors
deliberately use coarser labels. Extract only truly shared safe primitives into
the neutral owner if needed; do not import conformance into runtime or expose
provider class names globally. Likewise `_bounded_model_message` bounds and
escapes text but cannot make arbitrary validator prose secret-free.

## Handling rules and extensibility seams

- Raise where a failure is discovered; translate where its meaning changes;
  record it once at the boundary responsible for handling it. Expected input
  rejection, missing optional files and normal control flow do not need error
  tracebacks. DEBUG is safe detail, INFO normal lifecycle, WARNING a recoverable
  degradation, ERROR a failed operation, CRITICAL inability to continue.
  Diagnostic severity and exception ancestry do not automatically choose a log
  level, HTTP status, retry policy or process exit status.
- Keep narrow catches when the failure set is known. Broad catches at hostile
  backend/resolver boundaries may be necessary to fail closed. Cleanup catches
  of `BaseException` that roll back and re-raise must still cover cancellation,
  `KeyboardInterrupt` and `SystemExit`; never normalize those indiscriminately.
  Preserve `ExceptionGroup` and task-cancellation semantics. Do not replace
  indeterminate remote effects with a generic failure or retry them implicitly.
- Keep Temporal `workflow.logger`, deterministic workflow execution and
  replay suppression. Share event content/policy through that supported seam;
  do not replace it with a plain logger or run configuration/I/O in a workflow.
  Preserve the existing single-attempt delivery and recovery decisions.
- Configure level, output format and an application-owned stream/handler at
  startup. This seam supports a later host-selected sink without re-editing
  domain code or inventing a telemetry exporter now. Use module logger names
  and bounded, approved operation/run identifiers where correlation is needed;
  reuse existing operation context rather than adding a competing ID schema.
  Any task-local context must reset on exit and propagate deliberately through
  existing thread/worker boundaries; it must not bleed across requests.
- Structured extras, lazy message arguments and exception formatting all need
  the same safe-field rules. Prevent CR/LF/terminal-control injection, bound
  field sizes and event volume, and keep logging failure handling nonrecursive.
  A formatter regex alone cannot remove secrets from arbitrary object reprs,
  traceback chains or records reaching a different handler.

## Verification guardrails and non-goals

The implementation PR needs a repository-wide accounting of owned exception
families and raise/catch/output sites, including justified builtin/framework
cases. A grep showing no direct logging imports cannot establish correct
handling. Test externally visible behavior, not that every module calls a
wrapper. Extend existing parser/diagnostic, CLI/MCP, import-safety, API trust
boundary, request-limit, store/recovery and Temporal tests. Include secret
sentinels in actual captured logs and protocol responses, chained/provider and
validation failures, repeated startup configuration, host handlers, concurrent
context isolation, rollback/cancellation and logger/sink failure cases.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`,
the existing nox feedback lanes and existing CI/review gates. This run has no
requirement UID: do not fabricate one. Local checks stay targeted; full,
integration, fuzz and completion suites belong in CI. Published schema changes
would require the existing publication ledger and generation parity gates;
the shared Python exception tree does not itself require a wire schema change.

Non-goals: changing SDL validity/advisory classification, diagnostic/result
schemas, authorization rules, audit durability, persistence formats, retry or
workflow semantics; adding middleware frameworks, registries, a universal
error DTO, collectors, dependencies, hosting or telemetry services. Operational
logs are not scenario-native observability, participant observations, captured
evidence or derived measures (ADR-066). Keep framework control exceptions and
intentional foreign failures in test doubles. Do not catch everything at each
layer, log-and-rethrow repeatedly, monkey-patch dependency exceptions, wrap all
printing/warnings, or weaken policy gates to force uniform-looking code.

## Official-source basis

Checked 2026-10-28; these support the guidance, not a claim that the unimplemented
migration already meets the acceptance criteria.

- [Python 3.14 Logging HOWTO](https://docs.python.org/3.14/howto/logging.html):
  logger ownership, levels, library configuration and ordinary command output.
- [Python 3.14 builtin exceptions](https://docs.python.org/3.14/library/exceptions.html):
  `Exception` roots, inheritance cautions, causes and exception groups.
- [Python logging configuration security](https://docs.python.org/3.14/library/logging.config.html#security-considerations):
  configuration can instantiate arbitrary Python objects; it is trusted code.
- [Pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/)
  and [v2 migration](https://docs.pydantic.dev/latest/migration/#typeerror-is-no-longer-converted-to-validationerror-in-validators):
  validator exception contracts and `TypeError` behavior.
- [Temporal Python observability](https://docs.temporal.io/develop/python/observability#log-from-a-workflow):
  workflow logging must preserve replay-aware SDK behavior.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html):
  sensitive-data exclusion, injection resistance, bounded events, sink failure
  testing and access-controlled log handling.
