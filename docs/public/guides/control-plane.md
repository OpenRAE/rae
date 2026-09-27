# Serve the runtime control plane

The optional P2 HTTP adapter serves one durable P1 control-plane core. It is an
administration and service interface for a trusted host application. It is not
a participant API.

[API-404](https://github.com/OpenRAE/rae/blob/main/docs/requirements/API-404/requirement.md)
owns the guarantees. The
[trust-boundary decision](https://github.com/OpenRAE/rae/blob/main/docs/decisions/issue-1356-control-plane-participant-access-preflight.md)
owns the route and release rules. Follow them if this guide seems to differ.

## Keep participants behind your host

Participant clients call your application, not RAES. Your host authenticates
its own caller. It selects the run, participant, exact episode, audience, and
operation that caller may use. It calls RAES with a private service identity.
It releases only an authorized, governed result.

Never give a browser, participant agent, plugin, or mobile client a P2 token or
proxy identity. Never give one the `RuntimeControlPlane` object or its store.
Possession of any of these is administrative access.

RAES does not authenticate your end users. An organizational host keeps its
users, groups, tenants, sessions, and policy. A local host applies its own
caller boundary. A P2 identity is not an SDL participant, controller, or role.

## Know what each route admits

Every served route declares exactly one transport authority. The adapter
refuses to start if a route declares none or more than one.

| Authority | Admitted roles | Routes |
| --- | --- | --- |
| `public-probe` | none | `GET /health/live`, `GET /health/ready` |
| `administrative-read` | backend, operator, auditor | `GET /snapshot`, `/apparatus/operational-summary`, `/operations/{operation_id}`, `/participant-executions/{execution_scope_ref}`, and participant `status`, `history`, and `context` views |
| `administrative-mutation` | backend, operator | Operation submission, workflow cancellation and timeouts, participant episode lifecycle, control occurrences, and participant execution control |
| `operator-resolution` | operator | `POST /operations/{operation_id}/resolution` |

Every authenticated route also requires an identity bound to this exact
target. FastAPI's `/openapi.json`, `/docs`, and `/redoc` describe the API. They
carry no runtime state.

The core applies further checks after admission:

- Operation readback requires the original actor and authorization scope.
  Another actor gets the same `404` as an unknown operation.
- A control occurrence requires a matching participant/controller binding.
- With a crossing-policy resolver, a participant view requires exactly one
  matching participant/audience binding. RAES commits the API-423 crossing
  before it writes the view.

A read role admits the full snapshot, even when the identity also carries an
audience binding. An identity with bindings but no role is refused on every
route. There is no participant-limited P2 credential.

`app.state.control_plane_route_authority` maps each `(method, path)` to its
authority. Use it to build a proxy allowlist for your host's outbound calls.

## Configure service identities

```python
from raes_runtime import ControlPlaneProfile
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
    ParticipantAudienceSubjectBinding,
)

host_service = ControlPlaneIdentity(
    identity="host-service",
    roles=frozenset({ControlPlaneRole.BACKEND}),
    target_name=control_plane.target_name,
    participant_audience_subjects=(
        ParticipantAudienceSubjectBinding("participant.alice", "audience:alice-console"),
    ),
)
security = ControlPlaneSecurityConfig(
    bearer_tokens={secret_store.read("raes-host-token"): host_service},
)
app = create_control_plane_app(control_plane, security=security, profile=ControlPlaneProfile.P2)
```

Load each bearer token from your deployment's secret channel. Use a frozenset
for roles and tuples for bindings. The configuration refuses mistyped or
mutable authority fields. It also refuses an identity name or binding set that
exceeds the operation record limits: 256 characters per name or scope entry,
and 64 scope entries. A participant address in a binding cannot contain `:`.
An unknown bearer token fails with `401`. It never falls back to proxy headers.

Enable `trust_proxy_identity_headers` only behind a proxy that strips
client-supplied identity headers and sets verified ones.
`ControlPlaneSecurityConfig.strict_defaults()` trusts no token or header.

## Release participant views safely

- Configure a crossing-policy resolver before any participant-facing use.
  Without one, `status`, `history`, and `context` return legacy administrative
  projections. Do not release them to a participant.
- Check the returned participant, episode, and source state cut against your
  selection before release.
- Reauthorize every release, including cached, retried, and replayed results.
  A same-key replay returns the retained view to its original actor only.
- Never turn a snapshot, operation record, history, receipt, or error into a
  participant view by filtering it.

## Deploy the adapter

- Serve P2 on an administration or service network. Participants must not
  reach its socket.
- End TLS at your proxy. Authenticate service callers there as well.
- Run one worker with reload disabled. The adapter refuses a multi-worker
  environment.
- Keep tokens out of URLs, process arguments, environment dumps, logs, crash
  reports, fixtures, backups, and SDL.
- Every response carries `Cache-Control: no-store`. Do not configure proxy
  caching for this API.
- Scope any host cache by caller or session, run, participant, episode,
  audience, policy, and source revision. Invalidate it when any of them changes.
- Return your own participant-safe errors. Do not forward RAES errors, and do
  not let `403` or `404` reveal whether another participant exists.
- Keep the store directory private. Treat store backups as privileged.

## Add a route to the adapter

Declare one transport authority with the dependencies in
`raes_runtime.control_plane_api._auth`. A public probe is GET-only and must
return no runtime value. Then apply the operation's own subject policy in the
core. A stream, callback, or export must authorize every item it releases.
