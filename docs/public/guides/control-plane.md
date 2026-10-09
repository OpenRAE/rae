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
refuses to start if a route declares none or more than one. Each authority also
serves only its own HTTP methods: `public-probe` and `administrative-read` serve
only `GET`, and the other two serve only `POST`, `PUT`, `PATCH`, or `DELETE`.

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
It refuses a token or identity name with leading or trailing whitespace, so
strip a trailing newline from a secret file before you use it. The two trust
flags must be real `bool` values, and the size and queue limits must be `int`
values; parse strings from environment variables or YAML before you pass them.
An unknown bearer token fails with `401`. It never falls back to proxy headers.

Every transport-admission refusal returns the same body for its status: `401`
is always `unauthorized`, and `403` is always `forbidden`. The specific reason
goes only to the audit log. A malformed request body gets `422` only after the
caller is admitted.

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

## Bound request bodies

The adapter checks the size of every HTTP request before it routes,
authenticates, or parses it. The check covers every method and path: the
public probes, the API description routes, and paths that match no route.
`ControlPlaneSecurityConfig.max_request_bytes` sets the limit. The default is
1,000,000 bytes.

- **Declared length.** A request gets `400` with `invalid content-length` when
  it has more than one `Content-Length` header or a value that is not plain
  digits. A declared length above the limit gets `413` before the adapter reads
  any of the body.
- **Counted bytes.** The adapter counts the body bytes that the ASGI server
  delivers, whatever the header says. When a chunk would take the total past
  the limit, the adapter returns `413` with `request too large`. It does not
  keep that chunk or read the rest of the body.
- **Buffering.** The adapter holds an accepted body in memory, up to the limit.
  Then it passes the whole body to the route as one message. A route never sees
  part of a body. The adapter does not stream a body to a route.
- **Disconnects.** If the server reports a disconnect before the adapter has
  read the last chunk of the body, the adapter drops what it has read. No route
  runs, and no response is sent. This can happen even after the client has sent
  the whole body. Once the adapter has read the last chunk, the route runs even
  if the client then leaves. Send each mutation with an `Idempotency-Key`
  header, and reuse it when you retry.
- **Rejections.** Every `400` or `413` from this check has the same body for its
  status and carries `Cache-Control: no-store`. No route runs. The adapter
  audits the rejection as an `anonymous` `http-request-rejected` event. When
  that audit write fails or its queue is full, the response stays the same. The
  log gets a fixed message with no error details.

Your ASGI server and proxy own the rest of this boundary:

- Set a proxy body limit no larger than `max_request_bytes`.
- Limit header size, request time, idle time, and open connections. The adapter
  sets no time limit on a slow body, and each open request can buffer up to
  `max_request_bytes`.
- The server parses HTTP framing, such as chunked bodies and requests that send
  both `Content-Length` and `Transfer-Encoding`. The adapter sees only the
  body bytes that the server passes on.
- After a rejection, the adapter stops reading the body. The server decides
  whether to read and discard the rest or to close the connection.

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

The adapter is one process that owns one store. It provides no high
availability and no operation by several owners or workers. RAES does not
guarantee that a backend effect happens exactly once, and it never replays one.
After a crash, an operation whose effect cannot be established becomes
`INDETERMINATE` and keeps that state. To resolve it, an operator calls
`POST /operations/{operation_id}/resolution`. That call records a separate,
linked operation and leaves the original unchanged. TLS and proxy correctness
belong to your deployment.

## Add a route to the adapter

Register the route inside `create_control_plane_app()`, before the adapter
checks its route inventory. Do not change the returned app. Its routes,
middleware, exception handlers, and dependency overrides are sealed at
construction; after any change, startup fails and every request gets a redacted
`500`. Declare one transport authority with the dependencies in
`raes_runtime.control_plane_api._auth`. A public probe is GET-only and must
return no runtime value. Then apply the operation's own subject policy in the
core. A stream, callback, or export must authorize every item it releases.
