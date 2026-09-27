"""Served control-plane trust-boundary enforcement (issue #1359, API-404-C3).

The accepted exposure model is host-mediated, administrative-only P2 (#1356).
Every route that reveals runtime state or causes an effect admits only a
privileged, target-bound service identity. Participant/audience and
participant/controller bindings narrow a core operation after that admission;
they never make a credential participant-limited. These tests drive the real
ASGI boundary rather than the auth helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from participant_crossing_fixtures import (
    AUDIENCE,
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    evidence,
    policy_capable_target,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime import control_plane_api
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api._auth import (
    _administrative_read_dependency,
    _AdministrativeMutationIdentity,
    _AdministrativeReadIdentity,
    _PublicProbe,
)
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneRouteAuthority,
    ControlPlaneSecurityConfig,
    ParticipantAudienceSubjectBinding,
    ParticipantControlSubjectBinding,
)
from starlette.responses import PlainTextResponse
from starlette.routing import Mount
from starlette.testclient import TestClient
from test_run_310_supervisory_lifecycle import (
    _PARTICIPANT as _CONTROLLED_PARTICIPANT,
)
from test_run_310_supervisory_lifecycle import (
    _SPEC_ADDRESS,
    _compiled_specification,
    _proposal_body,
)

pytestmark = pytest.mark.control_plane_conformance

_TARGET = "stub"
_ALICE = "participant.alice"
_NO_STORE = "no-store"
_PUBLIC = ControlPlaneRouteAuthority.PUBLIC_PROBE
_READ = ControlPlaneRouteAuthority.ADMINISTRATIVE_READ
_MUTATE = ControlPlaneRouteAuthority.ADMINISTRATIVE_MUTATION
_RESOLVE = ControlPlaneRouteAuthority.OPERATOR_RESOLUTION

# The accepted route/authority matrix. A route added without updating this
# table fails the inventory test; a route added without a transport authority
# fails app construction.
_EXPECTED_ROUTE_AUTHORITY = {
    ("GET", "/health/live"): _PUBLIC,
    ("GET", "/health/ready"): _PUBLIC,
    ("POST", "/operations/provisioning"): _MUTATE,
    ("POST", "/operations/orchestration"): _MUTATE,
    ("POST", "/operations/evaluation"): _MUTATE,
    ("POST", "/operations/{operation_id}/resolution"): _RESOLVE,
    ("GET", "/operations/{operation_id}"): _READ,
    ("GET", "/snapshot"): _READ,
    ("GET", "/apparatus/operational-summary"): _READ,
    ("POST", "/workflows/{workflow_address}/cancel"): _MUTATE,
    ("POST", "/workflows/reconcile-timeouts"): _MUTATE,
    ("POST", "/participants/{participant_address}/episodes/initialize"): _MUTATE,
    ("POST", "/participants/{participant_address}/episodes/reset"): _MUTATE,
    ("POST", "/participants/{participant_address}/episodes/restart"): _MUTATE,
    ("POST", "/participants/{participant_address}/episodes/terminate"): _MUTATE,
    ("POST", "/participants/{participant_address}/control-occurrences"): _MUTATE,
    ("POST", "/participant-executions/{execution_scope_ref}/control"): _MUTATE,
    ("GET", "/participant-executions/{execution_scope_ref}"): _READ,
    ("GET", "/participants/{participant_address}/status"): _READ,
    ("GET", "/participants/{participant_address}/episodes/{episode_id}/history"): _READ,
    ("GET", "/participants/{participant_address}/context"): _READ,
}

# One concrete request per authenticated route: (method, template, path, json).
_ROUTE_REQUESTS: tuple[tuple[str, str, str, object], ...] = (
    (
        "POST",
        "/operations/provisioning",
        "/operations/provisioning",
        {"operations": [], "diagnostics": [], "realization_authority": []},
    ),
    (
        "POST",
        "/operations/orchestration",
        "/operations/orchestration",
        {"operations": [], "startup_order": [], "diagnostics": []},
    ),
    ("POST", "/operations/evaluation", "/operations/evaluation", {"operations": [], "diagnostics": []}),
    ("POST", "/operations/{operation_id}/resolution", "/operations/op-unknown/resolution", {}),
    ("GET", "/operations/{operation_id}", "/operations/op-unknown", None),
    ("GET", "/snapshot", "/snapshot", None),
    ("GET", "/apparatus/operational-summary", "/apparatus/operational-summary", None),
    ("POST", "/workflows/{workflow_address}/cancel", "/workflows/workflow.unknown/cancel", {}),
    ("POST", "/workflows/reconcile-timeouts", "/workflows/reconcile-timeouts", None),
    (
        "POST",
        "/participants/{participant_address}/episodes/initialize",
        f"/participants/{_ALICE}/episodes/initialize",
        {},
    ),
    ("POST", "/participants/{participant_address}/episodes/reset", f"/participants/{_ALICE}/episodes/reset", {}),
    (
        "POST",
        "/participants/{participant_address}/episodes/restart",
        f"/participants/{_ALICE}/episodes/restart",
        {},
    ),
    (
        "POST",
        "/participants/{participant_address}/episodes/terminate",
        f"/participants/{_ALICE}/episodes/terminate",
        {},
    ),
    (
        "POST",
        "/participants/{participant_address}/control-occurrences",
        f"/participants/{_ALICE}/control-occurrences",
        {},
    ),
    (
        "POST",
        "/participant-executions/{execution_scope_ref}/control",
        "/participant-executions/execution.unknown/control",
        {},
    ),
    ("GET", "/participant-executions/{execution_scope_ref}", "/participant-executions/execution.unknown", None),
    ("GET", "/participants/{participant_address}/status", f"/participants/{_ALICE}/status", None),
    (
        "GET",
        "/participants/{participant_address}/episodes/{episode_id}/history",
        f"/participants/{_ALICE}/episodes/episode-1/history",
        None,
    ),
    (
        "GET",
        "/participants/{participant_address}/context",
        f"/participants/{_ALICE}/context?view_ref=view.alice",
        None,
    ),
)

_ALICE_AUDIENCE = ParticipantAudienceSubjectBinding(participant_address=_ALICE, audience_scope_ref=AUDIENCE)
_ALICE_CONTROL = ParticipantControlSubjectBinding(participant_address=_ALICE, controller_ref="controller.alice")


def _identity(name: str, *roles: ControlPlaneRole, target_name: str = _TARGET, **bindings: Any) -> ControlPlaneIdentity:
    return ControlPlaneIdentity(identity=name, roles=frozenset(roles), target_name=target_name, **bindings)


_TOKENS = {
    "backend-token": _identity("backend", ControlPlaneRole.BACKEND),
    "operator-token": _identity("operator", ControlPlaneRole.OPERATOR),
    "auditor-token": _identity("auditor", ControlPlaneRole.AUDITOR),
    # A read role plus an audience binding is still broad administrative authority.
    "audience-reader-token": _identity(
        "audience-reader",
        ControlPlaneRole.AUDITOR,
        participant_audience_subjects=(_ALICE_AUDIENCE,),
    ),
    # The would-be "participant-limited" credential: bindings, no route role.
    "participant-limited-token": _identity(
        "participant-limited",
        participant_audience_subjects=(_ALICE_AUDIENCE,),
        participant_control_subjects=(_ALICE_CONTROL,),
    ),
    "other-target-token": _identity(
        "other-target",
        ControlPlaneRole.BACKEND,
        ControlPlaneRole.OPERATOR,
        ControlPlaneRole.AUDITOR,
        target_name="another-target",
    ),
}
_ADMITTED_TOKEN = {_READ: "audience-reader-token", _MUTATE: "backend-token", _RESOLVE: "operator-token"}
_DENIED_ROLE_TOKENS = {
    _READ: (),
    _MUTATE: ("auditor-token",),
    _RESOLVE: ("backend-token", "auditor-token"),
}


def _bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def _stub_app(**security_overrides: Any) -> tuple[FastAPI, RuntimeControlPlane]:
    control_plane = RuntimeControlPlane(create_stub_target())
    security = ControlPlaneSecurityConfig(bearer_tokens=_TOKENS, **security_overrides)
    return create_control_plane_app(control_plane, security=security), control_plane


def _send(client: TestClient, method: str, path: str, body: object, headers: dict[str, str]) -> Any:
    if body is None:
        return client.request(method, path, headers=headers)
    return client.request(method, path, json=body, headers=headers)


def _route_requests(*authorities: ControlPlaneRouteAuthority) -> list[Any]:
    return [
        pytest.param(method, template, path, body, id=f"{method} {template}")
        for method, template, path, body in _ROUTE_REQUESTS
        if _EXPECTED_ROUTE_AUTHORITY[(method, template)] in authorities
    ]


# --- route inventory -------------------------------------------------------


def test_every_served_route_declares_the_accepted_transport_authority() -> None:
    app, _control_plane = _stub_app()

    assert dict(app.state.control_plane_route_authority) == _EXPECTED_ROUTE_AUTHORITY
    with pytest.raises(TypeError):
        app.state.control_plane_route_authority[("GET", "/rogue")] = _PUBLIC


def test_route_request_table_exercises_every_authenticated_route() -> None:
    covered = {(method, template) for method, template, _path, _body in _ROUTE_REQUESTS}
    authenticated = {key for key, authority in _EXPECTED_ROUTE_AUTHORITY.items() if authority is not _PUBLIC}

    assert covered == authenticated


def _with_extra_route(register: Callable[[FastAPI], None]) -> Callable[..., None]:
    incumbent = control_plane_api._register_workflow_routes

    def registrar(app: FastAPI, control_plane: RuntimeControlPlane) -> None:
        incumbent(app, control_plane)
        register(app)

    return registrar


def _unauthenticated_event_route(app: FastAPI) -> None:
    @app.get("/events")
    async def events() -> dict[str, str]:
        return {"state": "leaked"}


def _double_authority_route(app: FastAPI) -> None:
    @app.post("/operations/inject")
    async def inject(reader: _AdministrativeReadIdentity, writer: _AdministrativeMutationIdentity) -> None:
        del reader, writer


def _public_mutation_route(app: FastAPI) -> None:
    @app.post("/inject", dependencies=[_PublicProbe])
    async def inject() -> None:
        return None


def _shadowing_route(app: FastAPI) -> None:
    @app.get("/snapshot", dependencies=[_PublicProbe])
    async def public_snapshot() -> dict[str, str]:
        return {"state": "leaked"}


def _read_authority_mutation_route(app: FastAPI) -> None:
    # An auditor holds the read authority; it must never reach a state change.
    @app.post("/operations/inject")
    async def inject(reader: _AdministrativeReadIdentity) -> None:
        del reader


def _mutation_authority_safe_method_route(app: FastAPI) -> None:
    @app.get("/operations/inject")
    async def inject(writer: _AdministrativeMutationIdentity) -> None:
        del writer


def _mounted_route(app: FastAPI) -> None:
    app.router.routes.append(Mount("/export", routes=[]))


def _starlette_route(app: FastAPI) -> None:
    app.add_route("/raw", lambda _request: PlainTextResponse("raw"))


@pytest.mark.parametrize(
    "register",
    [
        pytest.param(_unauthenticated_event_route, id="no-authority"),
        pytest.param(_double_authority_route, id="two-authorities"),
        pytest.param(_public_mutation_route, id="public-mutation"),
        pytest.param(_read_authority_mutation_route, id="read-authority-mutation"),
        pytest.param(_mutation_authority_safe_method_route, id="mutation-authority-get"),
        pytest.param(_shadowing_route, id="duplicate-route"),
        pytest.param(_mounted_route, id="mount"),
        pytest.param(_starlette_route, id="undeclared-framework-route"),
    ],
)
def test_app_construction_fails_closed_for_undeclared_route_authority(
    monkeypatch: pytest.MonkeyPatch,
    register: Callable[[FastAPI], None],
) -> None:
    monkeypatch.setattr(control_plane_api, "_register_workflow_routes", _with_extra_route(register))

    with pytest.raises(ValueError, match="transport authority"):
        create_control_plane_app(RuntimeControlPlane(create_stub_target()))


def _late_route(app: FastAPI) -> None:
    @app.get("/late")
    async def late() -> dict[str, str]:
        return {"state": "leaked"}


def _late_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def late(request: Any, call_next: Any) -> Any:
        if request.url.path == "/late":
            return PlainTextResponse("leaked")
        return await call_next(request)


def _late_exception_handler(app: FastAPI) -> None:
    app.add_exception_handler(403, lambda _request, _exc: PlainTextResponse("leaked", status_code=200))


def _late_dependency_override(app: FastAPI) -> None:
    app.dependency_overrides[_administrative_read_dependency] = lambda: _TOKENS["auditor-token"]


_LATE_COMPOSITION = [
    pytest.param(_late_route, id="route"),
    pytest.param(_late_middleware, id="middleware"),
    pytest.param(_late_exception_handler, id="exception-handler"),
    pytest.param(_late_dependency_override, id="dependency-override"),
]


@pytest.mark.parametrize("tamper", _LATE_COMPOSITION)
def test_app_composition_changed_after_construction_is_never_served(tamper: Callable[[FastAPI], None]) -> None:
    app, _control_plane = _stub_app()
    tamper(app)
    client = TestClient(app, raise_server_exceptions=False)

    responses = [
        client.get("/late"),
        client.get("/snapshot"),
        client.get("/snapshot", headers=_bearer("auditor-token")),
    ]

    for response in responses:
        assert response.status_code == 500
        assert response.json() == {"detail": "internal server error"}
        assert response.headers["cache-control"] == _NO_STORE
    assert ("GET", "/late") not in app.state.control_plane_route_authority


@pytest.mark.parametrize("tamper", _LATE_COMPOSITION)
def test_app_composition_changed_after_construction_fails_startup(tamper: Callable[[FastAPI], None]) -> None:
    app, _control_plane = _stub_app()
    tamper(app)

    with pytest.raises(RuntimeError), TestClient(app):
        pass


@pytest.mark.parametrize("tamper", [_late_route, _late_dependency_override], ids=["route", "dependency-override"])
def test_running_app_refuses_requests_after_its_composition_changes(tamper: Callable[[FastAPI], None]) -> None:
    app, _control_plane = _stub_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/snapshot", headers=_bearer("auditor-token")).status_code == 200
        tamper(app)
        late = client.get("/late")
        unauthenticated = client.get("/snapshot")

    for response in (late, unauthenticated):
        assert response.status_code == 500
        assert response.headers["cache-control"] == _NO_STORE


# --- transport admission on every authenticated route -----------------------


@pytest.mark.parametrize(("method", "template", "path", "body"), _route_requests(_READ, _MUTATE, _RESOLVE))
def test_authenticated_routes_reject_unauthenticated_callers(
    method: str, template: str, path: str, body: object
) -> None:
    app, _control_plane = _stub_app()

    with TestClient(app) as client:
        response = _send(client, method, path, body, {})

    assert response.status_code == 401
    assert response.headers["cache-control"] == _NO_STORE


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(_bearer("revoked-token"), id="invalid-bearer"),
        pytest.param({"x-raes-client-identity": "backend-token", "x-raes-client-verified": "true"}, id="proxy-headers"),
        pytest.param({}, id="no-credential"),
    ],
)
def test_unauthenticated_refusals_do_not_reveal_the_reason(headers: dict[str, str]) -> None:
    app, control_plane = _stub_app()

    with TestClient(app) as client:
        response = client.get("/snapshot", headers=headers)
        audited_reason = control_plane.audit_log()[-1].reason

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}
    assert audited_reason != "unauthorized"


@pytest.mark.parametrize(("method", "template", "path", "body"), _route_requests(_MUTATE, _RESOLVE))
def test_malformed_bodies_are_refused_by_admission_before_validation(
    method: str, template: str, path: str, body: object
) -> None:
    del template, body
    app, _control_plane = _stub_app()
    malformed = {"content-type": "application/json"}

    with TestClient(app) as client:
        anonymous = client.request(method, path, content=b"{not-json", headers=malformed)
        other_target = client.request(
            method, path, content=b"{not-json", headers={**malformed, **_bearer("other-target-token")}
        )

    assert anonymous.status_code == 401
    assert anonymous.json() == {"detail": "unauthorized"}
    assert other_target.status_code == 403
    assert other_target.json() == {"detail": "forbidden"}
    assert anonymous.headers["cache-control"] == other_target.headers["cache-control"] == _NO_STORE


@pytest.mark.parametrize(("method", "template", "path", "body"), _route_requests(_READ, _MUTATE, _RESOLVE))
def test_authenticated_routes_reject_identities_bound_to_another_target(
    method: str, template: str, path: str, body: object
) -> None:
    app, _control_plane = _stub_app()

    with TestClient(app) as client:
        response = _send(client, method, path, body, _bearer("other-target-token"))

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}


@pytest.mark.parametrize(("method", "template", "path", "body"), _route_requests(_READ, _MUTATE, _RESOLVE))
def test_participant_bound_identity_without_route_role_is_refused_everywhere(
    method: str, template: str, path: str, body: object
) -> None:
    app, control_plane = _stub_app()

    with TestClient(app) as client:
        response = _send(client, method, path, body, _bearer("participant-limited-token"))
        episodes = control_plane.snapshot.participant_episode_results

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}
    assert response.headers["cache-control"] == _NO_STORE
    assert not episodes


@pytest.mark.parametrize(("method", "template", "path", "body"), _route_requests(_MUTATE, _RESOLVE))
def test_routes_refuse_roles_outside_their_transport_authority(
    method: str, template: str, path: str, body: object
) -> None:
    app, _control_plane = _stub_app()
    authority = _EXPECTED_ROUTE_AUTHORITY[(method, template)]

    with TestClient(app) as client:
        responses = [_send(client, method, path, body, _bearer(token)) for token in _DENIED_ROLE_TOKENS[authority]]

    assert responses
    assert all(response.status_code == 403 for response in responses)
    assert all(response.json() == {"detail": "forbidden"} for response in responses)


@pytest.mark.parametrize(("method", "template", "path", "body"), _route_requests(_READ, _MUTATE, _RESOLVE))
def test_administrative_identity_passes_transport_admission_on_every_route(
    method: str, template: str, path: str, body: object
) -> None:
    app, _control_plane = _stub_app()
    token = _ADMITTED_TOKEN[_EXPECTED_ROUTE_AUTHORITY[(method, template)]]

    with TestClient(app) as client:
        response = _send(client, method, path, body, _bearer(token))

    # The core, not transport admission, decides the remaining outcome.
    assert response.status_code not in {401, 403}
    assert response.headers["cache-control"] == _NO_STORE


def test_audience_bound_read_identity_is_broad_administrative_authority() -> None:
    """A read role plus an audience binding can read the full snapshot (API-404-C3).

    Deployments must therefore never hand such an identity to a participant.
    """

    app, _control_plane = _stub_app()

    with TestClient(app) as client:
        snapshot = client.get("/snapshot", headers=_bearer("audience-reader-token"))
        summary = client.get("/apparatus/operational-summary", headers=_bearer("audience-reader-token"))

    assert snapshot.status_code == 200
    assert summary.status_code == 200
    assert snapshot.headers["cache-control"] == summary.headers["cache-control"] == _NO_STORE


# --- route-bypass attempts -------------------------------------------------


def test_route_variants_and_untrusted_identity_headers_do_not_bypass_admission() -> None:
    app, _control_plane = _stub_app()
    spoofed = {"x-raes-client-verified": "true", "x-raes-client-identity": "backend"}

    with TestClient(app) as client:
        redirected = client.get("/snapshot/", follow_redirects=False)
        followed = client.get("/snapshot/")
        head = client.head("/snapshot")
        header_identity = client.get("/snapshot", headers=spoofed)
        bad_token_with_headers = client.get("/snapshot", headers={**spoofed, **_bearer("unknown-token")})

    assert redirected.status_code == 307
    assert followed.status_code == 401
    assert head.status_code == 405
    assert header_identity.status_code == 401
    assert bad_token_with_headers.status_code == 401


def test_public_probes_and_api_description_expose_no_runtime_state() -> None:
    app, control_plane = _stub_app()
    target_name = control_plane.target_name

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        description = client.get("/openapi.json")

    assert live.status_code == 200
    assert set(live.json()) == set(ready.json()) == {"status", "reasons"}
    assert live.headers["cache-control"] == ready.headers["cache-control"] == _NO_STORE
    for response in (live, ready, description):
        assert target_name not in response.text
        assert "run:" not in response.text


# --- operation readback, idempotency and errors ------------------------------


def test_operation_readback_and_replay_are_actor_scoped_and_uncacheable() -> None:
    app, _control_plane = _stub_app()
    initialize = f"/participants/{_ALICE}/episodes/initialize"
    headers = {**_bearer("backend-token"), "idempotency-key": "retry-1"}

    with TestClient(app) as client:
        first = client.post(initialize, json={"episode_id": "episode-a"}, headers=headers)
        replay = client.post(initialize, json={"episode_id": "episode-a"}, headers=headers)
        conflicting = client.post(initialize, json={"episode_id": "episode-b"}, headers=headers)
        operation_id = first.json()["operation_id"]
        owner = client.get(f"/operations/{operation_id}", headers=_bearer("backend-token"))
        other_actor = client.get(f"/operations/{operation_id}", headers=_bearer("audience-reader-token"))
        unknown = client.get("/operations/op-unknown", headers=_bearer("audience-reader-token"))

    assert first.status_code == replay.status_code == owner.status_code == 200
    assert replay.json()["operation_id"] == operation_id
    assert conflicting.status_code == 409
    assert other_actor.status_code == unknown.status_code == 404
    assert other_actor.json() == unknown.json()
    for response in (first, replay, conflicting, owner, other_actor):
        assert response.headers["cache-control"] == _NO_STORE


def test_rejected_and_failed_responses_are_uncacheable(monkeypatch: pytest.MonkeyPatch) -> None:
    app, control_plane = _stub_app(max_request_bytes=64)
    monkeypatch.setattr(control_plane, "get_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("secret")))

    with TestClient(app, raise_server_exceptions=False) as client:
        oversized = client.post(
            "/operations/provisioning",
            json={"operations": [], "padding": "x" * 128},
            headers=_bearer("backend-token"),
        )
        invalid = client.post(
            "/operations/provisioning",
            json={"operations": "not-a-list"},
            headers=_bearer("backend-token"),
        )
        failed = client.get("/snapshot", headers=_bearer("auditor-token"))

    assert (oversized.status_code, invalid.status_code, failed.status_code) == (413, 422, 500)
    for response in (oversized, invalid, failed):
        assert response.headers["cache-control"] == _NO_STORE
    assert "secret" not in failed.text


# --- participant views ------------------------------------------------------


class _ViewEvidenceResolver(StaticCrossingResolver):
    def resolve_participant_view_evidence(self, **_kwargs: object):
        return evidence()


def _governed_identity(name: str, *bindings: ParticipantAudienceSubjectBinding) -> ControlPlaneIdentity:
    return _identity(name, ControlPlaneRole.OPERATOR, participant_audience_subjects=bindings)


def _governed_app() -> tuple[FastAPI, RuntimeControlPlane]:
    target = policy_capable_target("participant_egress_projection", "participant_transformation")
    control_plane = action_plane(_ViewEvidenceResolver(), target=target)
    bound = ParticipantAudienceSubjectBinding(participant_address=PARTICIPANT, audience_scope_ref=AUDIENCE)
    other = ParticipantAudienceSubjectBinding(
        participant_address="participant.behavior.other", audience_scope_ref=AUDIENCE
    )
    security = ControlPlaneSecurityConfig(
        bearer_tokens={
            "bound-token": _governed_identity("bound", bound),
            "other-participant-token": _governed_identity("other-participant", other),
            "unbound-token": _governed_identity("unbound"),
            "ambiguous-token": _governed_identity(
                "ambiguous",
                bound,
                ParticipantAudienceSubjectBinding(participant_address=PARTICIPANT, audience_scope_ref="audience:other"),
            ),
            "participant-limited-token": _identity(
                "participant-limited",
                participant_audience_subjects=(bound,),
            ),
        }
    )
    return create_control_plane_app(control_plane, security=security), control_plane


def _crossings(control_plane: RuntimeControlPlane) -> int:
    return len(control_plane.snapshot.participant_crossing_history.get(PARTICIPANT, ()))


def test_governed_view_is_bound_to_one_participant_without_an_existence_oracle() -> None:
    app, _control_plane = _governed_app()

    with TestClient(app) as client:
        bound = client.get(f"/participants/{PARTICIPANT}/status", headers=_bearer("bound-token"))
        other = client.get(f"/participants/{PARTICIPANT}/status", headers=_bearer("other-participant-token"))
        unknown = client.get("/participants/participant.behavior.unknown/status", headers=_bearer("bound-token"))
        unbound = client.get(f"/participants/{PARTICIPANT}/status", headers=_bearer("unbound-token"))
        limited = client.get(f"/participants/{PARTICIPANT}/status", headers=_bearer("participant-limited-token"))
        ambiguous = client.get(f"/participants/{PARTICIPANT}/status", headers=_bearer("ambiguous-token"))

    assert bound.status_code == 200
    assert bound.json()["participant_address"] == PARTICIPANT
    denied = (other, unknown, unbound, limited)
    assert all(response.status_code == 403 for response in denied)
    assert {response.text for response in denied} == {'{"detail":"forbidden"}'}
    assert ambiguous.status_code == 409
    for response in (bound, *denied, ambiguous):
        assert response.headers["cache-control"] == _NO_STORE


def test_governed_view_rejects_an_episode_outside_the_bound_participant_state() -> None:
    app, _control_plane = _governed_app()

    with TestClient(app) as client:
        current = client.get(
            f"/participants/{PARTICIPANT}/episodes/episode-1/history",
            headers=_bearer("bound-token"),
        )
        history = client.get(
            f"/participants/{PARTICIPANT}/episodes/episode-missing/history",
            headers=_bearer("bound-token"),
        )
        context = client.get(
            f"/participants/{PARTICIPANT}/context",
            params={"view_ref": "view.red", "episode_id": "episode-missing"},
            headers=_bearer("bound-token"),
        )

    assert current.status_code == 200
    assert current.json()["episode_id"] == "episode-1"
    assert history.status_code == context.status_code == 404


def test_governed_view_replay_returns_the_retained_view_only_within_its_scope() -> None:
    app, control_plane = _governed_app()
    path = f"/participants/{PARTICIPANT}/status"

    with TestClient(app) as client:
        first = client.get(path, headers={**_bearer("bound-token"), "idempotency-key": "view-1"})
        after_first = _crossings(control_plane)
        replay = client.get(path, headers={**_bearer("bound-token"), "idempotency-key": "view-1"})
        after_replay = _crossings(control_plane)
        cross_scope = client.get(path, headers={**_bearer("other-participant-token"), "idempotency-key": "view-1"})
        after_cross_scope = _crossings(control_plane)

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert after_replay == after_first
    assert cross_scope.status_code == 403
    assert after_cross_scope == after_first
    assert replay.headers["cache-control"] == _NO_STORE


def test_legacy_view_without_a_resolver_is_an_administrative_read_only() -> None:
    app, control_plane = _stub_app()

    with TestClient(app) as client:
        client.post(f"/participants/{_ALICE}/episodes/initialize", json={}, headers=_bearer("backend-token"))
        administrative = client.get(f"/participants/{_ALICE}/status", headers=_bearer("auditor-token"))
        limited = client.get(f"/participants/{_ALICE}/status", headers=_bearer("participant-limited-token"))
        crossings = control_plane.snapshot.participant_crossing_history

    assert administrative.status_code == 200
    assert administrative.json()["participant_address"] == _ALICE
    assert not crossings
    assert limited.status_code == 403


def test_audience_binding_is_not_participant_control_authority() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )
    audience_only = _identity(
        "audience-only",
        ControlPlaneRole.OPERATOR,
        participant_audience_subjects=(
            ParticipantAudienceSubjectBinding(participant_address=_CONTROLLED_PARTICIPANT, audience_scope_ref=AUDIENCE),
        ),
    )
    app = create_control_plane_app(
        control_plane,
        security=ControlPlaneSecurityConfig(bearer_tokens={"audience-only-token": audience_only}),
    )

    with TestClient(app) as client:
        response = client.post(
            f"/participants/{_CONTROLLED_PARTICIPANT}/control-occurrences",
            json=_proposal_body(),
            headers={**_bearer("audience-only-token"), "idempotency-key": "control-1"},
        )
        history = control_plane.snapshot.participant_control_history

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}
    assert not history


# --- configured principal shape --------------------------------------------


def _audience_bindings(count: int, *, ref_length: int = 16) -> tuple[ParticipantAudienceSubjectBinding, ...]:
    return tuple(
        ParticipantAudienceSubjectBinding(
            participant_address=f"participant.p{index}", audience_scope_ref="a" * ref_length
        )
        for index in range(count)
    )


_MALFORMED_PRINCIPALS: dict[str, Callable[[], ControlPlaneIdentity]] = {
    "mutable-roles": lambda: ControlPlaneIdentity(
        identity="mutable-roles",
        roles={ControlPlaneRole.BACKEND},  # type: ignore[arg-type]
        target_name=_TARGET,
    ),
    "string-role": lambda: ControlPlaneIdentity(
        identity="string-role",
        roles=frozenset({"backend"}),  # type: ignore[arg-type]
        target_name=_TARGET,
    ),
    "empty-target": lambda: _identity("empty-target", ControlPlaneRole.BACKEND, target_name=""),
    "non-string-target": lambda: _identity("typed-target", target_name=7),  # type: ignore[arg-type]
    "mutable-audience-bindings": lambda: _identity(
        "mutable-audience",
        participant_audience_subjects=[_ALICE_AUDIENCE],
    ),
    "mistyped-control-bindings": lambda: _identity(
        "mistyped-control",
        participant_control_subjects=(_ALICE_AUDIENCE,),
    ),
    # Downstream operation-context bounds: actor and each scope entry are at most
    # 256 characters and a scope holds at most 64 entries.
    "over-bound-identity": lambda: _identity("a" * 257, ControlPlaneRole.AUDITOR),
    "over-bound-scope-entry": lambda: _identity(
        "long-audience",
        ControlPlaneRole.AUDITOR,
        participant_audience_subjects=_audience_bindings(1, ref_length=256),
    ),
    "too-many-scope-entries": lambda: _identity(
        "many-audiences",
        ControlPlaneRole.AUDITOR,
        participant_audience_subjects=_audience_bindings(64),
    ),
}


@pytest.mark.parametrize("principal", list(_MALFORMED_PRINCIPALS), ids=list(_MALFORMED_PRINCIPALS))
@pytest.mark.parametrize("mapping", ["bearer_tokens", "trusted_identities"])
def test_security_config_rejects_malformed_principal_shapes(principal: str, mapping: str) -> None:
    secret = "credential-value-1359"

    with pytest.raises(ValueError, match="configured principal") as caught:
        ControlPlaneSecurityConfig(**{mapping: {secret: _MALFORMED_PRINCIPALS[principal]()}})

    assert secret not in str(caught.value)


@pytest.mark.parametrize("field", ["require_verified_identity", "trust_proxy_identity_headers"])
@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_security_config_rejects_non_bool_trust_flags(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"{field} must be a bool"):
        ControlPlaneSecurityConfig(**{field: value})


@pytest.mark.parametrize("field", ["max_request_bytes", "max_pending_mutations", "max_pending_rejection_audits"])
@pytest.mark.parametrize("value", ["64", 1.5, True])
def test_security_config_rejects_non_int_limits(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"{field} must be an int"):
        ControlPlaneSecurityConfig(**{field: value})


@pytest.mark.parametrize("mapping", ["bearer_tokens", "trusted_identities"])
@pytest.mark.parametrize("key", ["secret\n", " secret", "secret\t"])
def test_security_config_rejects_padded_credentials(mapping: str, key: str) -> None:
    with pytest.raises(ValueError, match="unpadded") as caught:
        ControlPlaneSecurityConfig(**{mapping: {key: _identity("padded", ControlPlaneRole.AUDITOR)}})

    assert "secret" not in str(caught.value)


def test_principal_at_the_operation_context_bounds_is_admitted() -> None:
    principal = _identity(
        "a" * 256,
        ControlPlaneRole.AUDITOR,
        participant_audience_subjects=_audience_bindings(63),
    )
    app = create_control_plane_app(
        RuntimeControlPlane(create_stub_target()),
        security=ControlPlaneSecurityConfig(bearer_tokens={"bounded-token": principal}),
    )

    with TestClient(app) as client:
        response = client.get("/snapshot", headers=_bearer("bounded-token"))

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("participant_address", "subject_ref", "message"),
    [
        (["participant.alice"], "audience:alice", "must be strings"),
        ("participant.alice", 7, "must be strings"),
        ("", "audience:alice", "must be non-empty"),
        ("participant:alice", "audience:alice", "must not contain ':'"),
    ],
)
@pytest.mark.parametrize("binding_type", [ParticipantAudienceSubjectBinding, ParticipantControlSubjectBinding])
def test_subject_bindings_reject_fields_that_cannot_encode_an_unambiguous_scope(
    binding_type: type,
    participant_address: object,
    subject_ref: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        binding_type(participant_address, subject_ref)
