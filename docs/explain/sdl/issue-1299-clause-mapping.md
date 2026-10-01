# Issue 1299 Clause Mapping: Partial Listener Descriptions

## Decision

`runtime.service_listeners` is a descriptive inventory surface, not universal
endpoint admission. Only `service_listener_id` is universally required.
Supplied facts retain their bounds, closed-object shape, reference integrity,
and known contradictions; omitted facts remain omitted. A backend operation or
complete-report assessment that needs a usable endpoint owns the corresponding
completeness precondition.

The existing `tcp` model default remains for compatibility. Source-preserving
rendering omits it when unauthored, and instantiated explicitness provenance
prevents that default from becoming an exact author claim. `unknown` and
`other` defer protocol agreement; a private concrete vocabulary value remains
an exact value and is compared.

## Alternatives considered

- Requiring address or interface plus port on every network listener was
  rejected because inventory collectors and authored constraints can know only
  part of an endpoint.
- Treating every non-`unix` protocol as a network endpoint was rejected because
  `unknown`, `other`, variables, and private vocabulary values do not prove an
  address family.
- Synthesizing wildcard addresses, ports, interfaces, publications, or service
  bindings was rejected because it would turn missing knowledge into a false
  deployment or observation claim.
- Removing the legacy `tcp` default was rejected as an unnecessary source and
  instantiated-contract compatibility break.

## External-practice check

Host and remote inventory sources expose different slices of listener state.
Linux `/proc/net/tcp` exposes local address and port in a host-local table;
osquery/Fleet publishes address, port, protocol, family, and process ownership
as separate columns; Nmap reports reachability state from the scanner's
vantage. Those sources support preserving known fields independently rather
than requiring one globally complete endpoint tuple.

- Linux kernel `proc_net_tcp` documentation:
  <https://docs.kernel.org/networking/proc_net_tcp.html>
- Fleet `listening_ports` table:
  <https://fleetdm.com/tables/listening_ports>
- Nmap port-scanning states:
  <https://nmap.org/book/man-port-scanning-basics.html>

## Acceptance-clause mapping

| Issue clause | Implementation and verification |
| --- | --- |
| Partial TCP, Unix, unknown, private, and explicit-empty descriptions parse and round-trip | `RuntimeServiceListener.validate_listener_shape`; `test_partial_listener_knowledge_parses_and_round_trips_without_invented_facts` |
| Bounds and supplied Unix/network, family, and scope contradictions remain enforced | `RuntimeServiceListener.validate_listener_shape` plus provenance-aware TCP-default checks in `SemanticValidator`; existing listener validation tests plus `test_partial_unix_listener_permits_missing_path_but_rejects_network_fields` and `test_listener_rejects_mixed_supplied_unix_and_network_shapes` |
| Optional service, process, publication, and relationship refs remain semantic refs | Existing service-listener semantic/reference tests; publication resolution remains unconditional for concrete reference tuples |
| Legacy TCP default survives without becoming authored knowledge | `test_omitted_legacy_tcp_default_is_source_absent_and_instantiated_default`; semantic comparisons consult source presence or instantiated explicitness |
| Open parents delegate omitted bind detail while retaining exact children | `test_open_listener_scope_delegates_bind_but_preserves_exact_port` |
| Missing/open protocol defers agreement; private concrete protocol binds | `test_missing_or_unknown_listener_protocol_defers_service_protocol_agreement` and `test_concrete_private_listener_protocol_remains_binding` |
| Partiality grants no access, publication, observation, retention, or export | `test_partial_listener_does_not_create_access_publication_or_capture_demand`; no policy, capture, lifecycle, or export surface is changed |
| Complete endpoint admission remains closed where selected | Backend preparation/installed validation or a coverage-aware complete-report assessment must require the fields its operation consumes; descriptive parsing does not satisfy that precondition |
| SSH disposition is explicit | `RuntimeSshServer.service` remains required; `test_ssh_daemon_policy_keeps_its_explicit_service_binding` prevents accidental loosening |
| Published schemas remain synchronized | Five generated contract schemas and their publication-ledger hashes are updated and schema-validated |

## Known limitation

RAES does not currently define one transport-neutral operation that consumes
every `runtime.service_listeners` entry as a complete endpoint. Completeness is
therefore intentionally local to a selected backend operation or a report that
claims complete endpoint coverage. Adding such an operation requires an
explicit precondition and negative tests for missing fields; it must not move
that requirement back into the descriptive model.
