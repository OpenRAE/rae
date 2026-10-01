# ADR-035: Service-Manager Unit State Runtime Surface

## Status

accepted

## Date

2026-05-26

## Context

Issue #418 identifies an SDL expressivity gap for service-manager unit state
observable from inside a realized range node. The motivating
Brad-Edwards/aptl#334 workstation evidence records `systemctl` facts such as:

- `sshd.service` loaded, enabled, and active/running with a live PID and
  listener evidence on TCP/22
- `lab-install.service` loaded/enabled but failed on first boot
- `rsyslog.service` failed with `status=226/NAMESPACE`
- `systemd-tmpfiles-*` units failed with setup or credential errors
- `systemd-user-sessions.service` active/exited
- Wazuh and Falco unit files present and disabled even though related software
  and configuration exist

Those facts are not equivalent to process inventory, package inventory,
transport services, Docker/container host configuration, authored checks, or
filesystem evidence. Failed, disabled, static, enabled-but-not-running, and
active/exited units may have no live process. Conversely, a live process or a
unit file does not by itself express the service manager's load state, enable
state, active/sub state, result, or failure status.

The repository already has adjacent surfaces:

- `Node.services` records transport service bindings such as SSH on TCP/22.
- `conditions` records authored monitoring/readiness checks.
- `runtime.process` and `runtime.processes` record observed process identity.
- `runtime.container` records container host/security and init facts.
- `runtime.operational_policy` records orchestrator restart/resource policy.
- `runtime.ssh_servers` records sshd policy, not generic unit lifecycle.
- `runtime.packages` and `runtime.software_components` record installed
  software identity.
- `runtime.filesystem_inventory` and `content` can record unit files and
  checksums.
- top-level `features` records authored scenario intent.

The design risk is to encode service-manager state by overloading one of those
nearby concepts and thereby confuse authored intent, installed software,
transport exposure, live processes, files-on-disk, and observed lifecycle
realization.

## Decision

### 1. Model unit state under node runtime

Service-manager unit state belongs under `Node.runtime` as a typed, node-scoped
runtime inventory, for example:

`Node.runtime.service_manager_units`

The inventory should use list records with stable identifiers rather than YAML
mapping keys. Each unit record should be able to preserve, when known:

- stable ACES unit id
- service-manager kind, initially including `systemd`
- native unit name such as `sshd.service`
- unit kind/type such as service, socket, timer, target, path, mount, or other
- load state
- enable/unit-file state
- active state and sub state
- result/failure class and bounded status detail
- main PID when a live process exists
- optional unit file path evidence
- optional command or `ExecStart` evidence with explicit redaction behavior
- optional same-node transport service refs when a unit is known to own a
  `Node.services[]` listener

This is observed WHAT-IS state. It is not a provisioning instruction, not a
condition check, and not an import of systemd as the SDL schema.

### 2. Keep adjacent concepts distinct

The implementation must preserve these boundaries:

- `Node.services` remains transport-level binding and naming. A unit may point
  at an owning service ref when useful, but must not mutate the service.
- `conditions` remains authored monitoring/readiness intent. It does not become
  an arbitrary `systemctl` state capture surface.
- `runtime.processes` remains live process observation. A unit can reference a
  PID as data, but failed, disabled, and active/exited units still need their
  own lifecycle record.
- `runtime.container.init_process` remains container PID-1/init configuration.
  Guest service-manager units are a different runtime layer.
- `runtime.operational_policy.restart` remains orchestrator lifecycle policy,
  not systemd restart policy or last unit result.
- `runtime.ssh_servers` remains SSH daemon policy. `sshd.service` lifecycle
  state does not replace SSH transport or sshd policy facts.
- `runtime.packages`, `runtime.software_components`, `content`, and
  `runtime.filesystem_inventory` remain software/file identity and evidence
  surfaces, not realized lifecycle state.
- top-level `features` remains authored scenario intent, not observed first-boot
  outcome.

### 3. Reuse existing SDL and contract gates

The implementation must reuse the repository's existing gates:

- `SDLModel` closed-world Pydantic validation and local field/model validators.
- shared parsing helpers in `runtime_values.py` and `_base.py`, including
  `require_symbol()`, `parse_int_or_var()`, `parse_bool_or_var()` where needed,
  `parse_runtime_enum_or_var()`, `absolute_path_or_var()`, and
  `coerce_string_list()`.
- parser key normalization, source-shorthand behavior, nested hashmap-key
  preservation, and variable-placeholder key rejection. Prefer list records so
  parser hashmap rules do not need to grow.
- `SemanticValidator` and `SDLValidationError` for any cross-reference checks,
  especially same-node service refs and optional filesystem-path checks when
  filesystem inventory is present.
- `instantiate_scenario()` and `SDLInstantiationError` for substitution and
  concrete revalidation.
- `compile_runtime_model()`'s existing node dump path so runtime metadata
  survives compilation without a parallel compiler pipeline.
- `schema_bundle()`, `tools/generate_contract_schemas.py`, and
  `tools/check_generated_schemas.py`; generated schemas under
  `contracts/schemas/` must not be edited directly.
- existing `aces_processor.models.Diagnostic`, runtime snapshots, control-plane
  envelopes, and MCP operation error shapes if unit facts later flow through
  reports, APIs, or tools.

No new parser, schema registry, validation framework, exception hierarchy,
logging stack, persistence mechanism, backend-specific systemd dialect, or
second workflow/control model is justified for this issue.

### 4. Validate state without leaking host details or secrets

Service-manager capture can expose sensitive command arguments, environment
files, credentials paths, journal excerpts, backend error text, and
operator-only filesystem paths. The portable SDL model must keep bounded fields
and explicit redaction controls rather than storing raw `systemctl status`,
`systemctl show`, journal output, unit-file text, or backend inspector payloads.

The security and validation gates are:

- Parser gate: hyphenated authoring names such as `service-manager-units`
  normalize through the existing parser. Symbol-defining ids are concrete
  values, not `${var}` placeholders or mapping keys.
- SDL model gate: stable ids reject empty values and variables; enum-like state
  fields use bounded portable vocabularies with `unknown`/`other` escape
  values; PIDs and status codes use existing integer-or-variable parsing;
  duplicate unit ids and native unit names in the same node are rejected.
- Semantic validation gate: service refs, if present, resolve only to same-node
  `Node.services[]` entries. Unit-file paths may be cross-checked against
  `runtime.filesystem_inventory` when that inventory is present.
- Instantiation gate: value placeholders can be deferred, but stable ids and
  mapping keys cannot. Instantiated scenarios revalidate after substitution.
- Contract/schema gate: generated schemas come from Python model sources and
  the schema bundle only.
- Host/OS exposure gate: unit state may record participant-observable lifecycle
  facts, but raw command lines, environment files, credentials, journal text,
  host-only paths, and backend payloads are omitted or redacted.
- Error-envelope gate: parse, validation, MCP, runtime snapshot, and
  control-plane failures use the existing redacted error and diagnostic
  envelopes rather than echoing raw service-manager output.

### 5. Keep the extensibility seam service-manager scoped

The extension seam is the node-scoped service-manager unit inventory,
parameterized by manager kind and native unit identity. A manager identity is
not proof that core SDL understands that manager's lifecycle state. Rich state
for a non-systemd manager uses an exact, admitted domain-profile definition;
it does not add an OpenRC, launchd, supervisord, or Windows-service catalog to
the core model.

Do not add a protocol-agnostic `service_config` dictionary or make
`ServicePort` carry unit lifecycle state unless a separate decision introduces
a broader service configuration abstraction across multiple concrete
protocols/managers.

### 6. Separate portable identity from the selected systemd state profile

`unit_id` is the stable portable row identity and the keyed comparison field.
`unit_name` is optional native data: preserve an exact supplied name without
normalizing it, adding a suffix, or using it as the row key. A native name must
be concrete and whitespace-free. Only an explicitly selected `systemd`
manager applies the systemd suffix and lifecycle-state contract.

The historical omitted-manager default remains readable as systemd
compatibility data, but omission is not an authored systemd choice. Presence
and inherited realization closure determine whether omitted manager, name, or
state leaves are delegated. Explicit `unknown`, omission, delegation, and an
exact private identity remain distinct. A private manager record may carry the
portable identity, native name, same-node service reference, unit-file path,
and description; it cannot use the flat systemd lifecycle or `ExecStart`
fields for non-default state.

This distinction is descriptive only. A valid row does not prove unit-file
presence, process existence, listener exposure, successful execution, or live
service-manager access.

## Guardrails

- Do not encode `lab-install.service failed`, `rsyslog.service failed`, or
  `systemd-user-sessions.service active/exited` as a transport service,
  process row, condition, package, content file, generic feature, or prose-only
  description.
- Do not infer unit lifecycle from package presence, unit-file checksums, or a
  process name. Record explicit unit state only when observed.
- Do not promote unit ids to generic relationship/objective target refs unless
  `_module_symbols.py`, `SemanticValidator._qualified_runtime_refs`, module
  namespacing, docs, and tests are updated together.
- Do not store raw `systemctl`, `journalctl`, unit-file, Docker, shell, or
  scanner output as the portable SDL model.
- Do not capture secret-bearing `ExecStart`, environment, credential, or
  failure output values without a redaction path that omits the raw value.
- Do not hand-edit generated schemas under `contracts/schemas/`.
- Do not add implementation logic under `implementations/python/src/aces/`;
  that tree is compatibility-only wrappers.

## Non-Goals

- Implementing issue #418.
- Updating `examples/scenarios/techvault.sdl.yaml` or downstream APTL
  inventories.
- Building a `systemctl`, systemd DBus, OpenRC, launchd, Windows Service
  Control Manager, journal, Docker, Compose, Podman, Kubernetes, or scanner
  discovery tool.
- Modeling every systemd unit property, dependency edge, journal event, cgroup
  detail, or retry/restart transition.
- Defining backend provisioning behavior for service-manager units.
- Redesigning `Node.services`, `conditions`, `runtime.processes`,
  `runtime.container`, `runtime.operational_policy`, `runtime.ssh_servers`,
  package/software inventory, runtime snapshots, or control-plane APIs.

## Consequences

### Positive

- Installed software, unit files, live processes, transport services, authored
  checks, and realized service-manager lifecycle state stay distinguishable.
- Failed, disabled, static, and active/exited units can be represented without
  inventing fake processes or services.
- Existing SDL parsing, validation, instantiation, schema generation,
  diagnostics, snapshots, MCP, and control-plane boundaries remain
  authoritative.

### Negative

- Node runtime gains another optional inventory surface.
- Consumers that care about operational readiness must inspect both transport
  services/processes and service-manager unit state when both are present.

### Risks

- A generic free-form service-manager dictionary would become a raw
  backend-output dumping ground.
- Overloading `Node.services` would erase the distinction between a listening
  transport endpoint and the manager unit that may or may not launch it.
- Capturing raw command lines, environment files, or journal output could leak
  secrets into examples, generated schemas, diagnostics, logs, snapshots, or
  audit records.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-17 | #1297 | Separated portable unit identity/native names from the explicitly selected systemd state profile and preserved omission semantics. |
