"""Observed application HTTP route/API/UI surface inventory models for SDL nodes.

These models express the participant-observable application-layer surface of a
range service (see ADR-026): HTTP route paths and methods, owning transport
service, auth/session requirements, typed request inputs, responses,
template/static asset associations,
route-visible fixture secrets or diagnostic disclosures, and redirect/error
behavior.

This is observed runtime state attached to ``Node.runtime``. It is distinct
from ``Node.services`` (transport bindings), ``runtime.network.published_ports``
(host/OS publication), and ``content`` (scenario data fixtures). External
weakness assertions use standalone generic bindings against the exact route
subject, never intrinsic route classification fields.
"""

from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_int_or_var,
)
from ._classification_guard import LegacyClassificationGuard
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import (
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
)
from .runtime_values import (
    require_symbol as _require_symbol,
)

__all__ = [
    "RelationshipProxyUpstream",
    "RuntimeApplicationDisclosure",
    "RuntimeApplicationExposedField",
    "RuntimeApplicationParameter",
    "RuntimeApplicationParameterLocation",
    "RuntimeApplicationProtocol",
    "RuntimeApplicationRedirect",
    "RuntimeApplicationResponse",
    "RuntimeApplicationRoute",
    "RuntimeApplicationRouteUpstreamScheme",
    "RuntimeApplicationRouteUpstreamTarget",
    "RuntimeApplicationSurface",
]

_MIN_STATUS_CODE = 100
_MAX_STATUS_CODE = 599
_MIN_REDIRECT_STATUS_CODE = 300
_MAX_REDIRECT_STATUS_CODE = 399

# Standard HTTP request methods (RFC 9110 + PATCH). Backend-observed surfaces
# normalize to this portable spelling; ``${var}`` placeholders pass through.
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"})

# Sensitivity classes whose raw value must never be recorded.
_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)


class RuntimeApplicationProtocol(str, Enum):
    """Application-layer protocol class for an observed application surface."""

    HTTP = "http"
    HTTPS = "https"
    WS = "ws"
    WSS = "wss"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeApplicationParameterLocation(str, Enum):
    """Where a request input is carried on an observed route."""

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    FORM = "form"
    JSON_BODY = "json_body"
    UPLOADED_FILE = "uploaded_file"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeApplicationRouteUpstreamScheme(str, Enum):
    """Wire scheme a reverse proxy uses to reach a route's upstream origin.

    This is a CLOSED taxonomy: an upstream is reached over either cleartext
    HTTP or TLS-wrapped HTTPS. Unlike the open ``RuntimeApplicationProtocol``,
    it carries neither ``other`` nor ``unknown`` — a proxy-to-origin hop that is
    neither HTTP nor HTTPS is not an application route upstream.
    """

    HTTP = "http"
    HTTPS = "https"


def _url_path_or_var(value: str, *, field_name: str, allow_empty: bool = False) -> str:
    """Validate a URL path, allowing ``${var}`` placeholders.

    URL paths are not filesystem paths: they must start with ``/`` and may carry
    framework path-variable markers (``<id>``/``{id}``). Whitespace is rejected.
    """
    if is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value:
        if allow_empty:
            return value
        raise ValueError(f"{field_name} must be a non-empty URL path")
    if not value.startswith("/"):
        raise ValueError(f"{field_name} must be a URL path starting with '/'")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must not contain whitespace")
    return value


class RuntimeApplicationParameter(SDLModel):
    """A typed request input observed on an application route.

    ``location`` distinguishes path variables, query string, headers, cookies,
    form fields, JSON body fields, and uploaded-file fields.
    """

    name: str
    location: RuntimeApplicationParameterLocation | str = RuntimeApplicationParameterLocation.OTHER
    required: bool | str | None = None
    data_type: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("parameter name must be a non-empty string")
        return v

    @field_validator("location", mode="before")
    @classmethod
    def normalize_location(
        cls,
        v: RuntimeApplicationParameterLocation | str,
    ) -> RuntimeApplicationParameterLocation | str:
        return parse_runtime_enum_or_var(v, RuntimeApplicationParameterLocation, field_name="location")

    @field_validator("required", mode="before")
    @classmethod
    def parse_required(cls, v: bool | str | None) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="required")


class RuntimeApplicationResponse(SDLModel):
    """An observed response a route can produce."""

    status_code: int | str
    content_type: str = ""
    description: str = ""

    @field_validator("status_code", mode="before")
    @classmethod
    def parse_status_code(cls, v: int | str) -> int | str:
        return parse_int_or_var(
            v,
            minimum=_MIN_STATUS_CODE,
            maximum=_MAX_STATUS_CODE,
            field_name="status_code",
        )


class RuntimeApplicationRedirect(SDLModel):
    """An observed redirect a route can issue.

    Target path/URL, status code, and the triggering condition are kept
    distinct; the target is recorded verbatim, never resolved.
    """

    target: str
    status_code: int | str | None = None
    condition: str = ""
    description: str = ""

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("redirect target must be a non-empty string")
        return v

    @field_validator("status_code", mode="before")
    @classmethod
    def parse_status_code(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(
            v,
            minimum=_MIN_REDIRECT_STATUS_CODE,
            maximum=_MAX_REDIRECT_STATUS_CODE,
            field_name="redirect status_code",
        )


class RuntimeApplicationDisclosure(SDLModel):
    """Observable error or information-disclosure behavior of a route.

    ``disclosure`` is a classified description of what the application exposes
    (a stack trace, an internal path, a backend version), never the raw payload,
    token, password, or cookie itself.
    """

    trigger: str = ""
    status_code: int | str | None = None
    disclosure: str = ""
    sensitivity: RuntimeSensitivityClassification | str = RuntimeSensitivityClassification.UNKNOWN
    description: str = ""

    @field_validator("status_code", mode="before")
    @classmethod
    def parse_status_code(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(
            v,
            minimum=_MIN_STATUS_CODE,
            maximum=_MAX_STATUS_CODE,
            field_name="disclosure status_code",
        )

    @field_validator("sensitivity", mode="before")
    @classmethod
    def normalize_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="sensitivity")


class RuntimeApplicationExposedField(SDLModel):
    """A route-visible fixture secret or intentionally exposed diagnostic field.

    The sensitivity vocabulary is shared with the rest of the runtime surface.
    A ``redacted`` or ``operator_secret`` field must omit its raw ``value``.
    Other values, including credential-shaped fixture facts, are scenario
    content needed for range realization and participant observation.
    """

    name: str
    sensitivity: RuntimeSensitivityClassification | str = RuntimeSensitivityClassification.UNKNOWN
    value: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("exposed field name must be a non-empty string")
        return v

    @field_validator("sensitivity", mode="before")
    @classmethod
    def normalize_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="sensitivity")

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "RuntimeApplicationExposedField":
        enforce_observed_value_redaction(
            owner_label=f"exposed field '{self.name}'",
            value=self.value,
            classification=self.sensitivity,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self


class RuntimeApplicationRouteUpstreamTarget(SDLModel):
    """The origin a reverse-proxied route forwards to.

    A proxy/gateway route does not itself serve content; it relays to an
    upstream origin on this or another node. ``target_node_ref`` /
    ``target_service`` name that origin (the service-name forms mirror
    ``RuntimeApplicationSurface.service``), ``scheme`` is the CLOSED
    proxy-to-origin wire scheme, and ``tls_terminated_here`` records whether
    TLS is terminated at the proxy (re-encrypted or plaintext to the origin).
    All fields are observation metadata; nothing is resolved.
    """

    target_node_ref: str = ""
    target_service: str = ""
    scheme: RuntimeApplicationRouteUpstreamScheme | str = RuntimeApplicationRouteUpstreamScheme.HTTP
    tls_terminated_here: bool | str | None = None

    @field_validator("scheme", mode="before")
    @classmethod
    def normalize_scheme(
        cls,
        v: RuntimeApplicationRouteUpstreamScheme | str,
    ) -> RuntimeApplicationRouteUpstreamScheme | str:
        return parse_runtime_enum_or_var(v, RuntimeApplicationRouteUpstreamScheme, field_name="scheme")

    @field_validator("tls_terminated_here", mode="before")
    @classmethod
    def parse_tls_terminated_here(cls, v: bool | str | None) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="tls_terminated_here")


class RuntimeApplicationRoute(LegacyClassificationGuard):
    """An observed application route — a participant-visible endpoint.

    ``route_id`` is the stable identity; ``path`` is data and may carry path
    variables, may be shared across HTTP methods, and is never a mapping key.
    """

    legacy_classification_fields = ("vulnerability_refs",)

    route_id: str
    path: str
    methods: list[str] = Field(default_factory=list)
    name: str = ""
    description: str = ""
    auth_required: bool | str | None = None
    auth_scheme: str = ""
    session_required: bool | str | None = None
    parameters: list[RuntimeApplicationParameter] = Field(default_factory=list)
    responses: list[RuntimeApplicationResponse] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)
    static_assets: list[str] = Field(default_factory=list)
    redirects: list[RuntimeApplicationRedirect] = Field(default_factory=list)
    disclosures: list[RuntimeApplicationDisclosure] = Field(default_factory=list)
    exposed_fields: list[RuntimeApplicationExposedField] = Field(default_factory=list)
    upstream_target: RuntimeApplicationRouteUpstreamTarget | None = None

    @field_validator("route_id")
    @classmethod
    def validate_route_id(cls, v: str) -> str:
        return _require_symbol(v, field_name="route_id")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return _url_path_or_var(v, field_name="route path")

    @field_validator("methods", mode="before")
    @classmethod
    def coerce_methods(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("methods")
    @classmethod
    def normalize_methods(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("route methods must not be empty")
        normalized: list[str] = []
        for method in v:
            if is_variable_ref(method):
                normalized.append(method)
                continue
            if not isinstance(method, str) or not method.strip():
                raise ValueError("route method must be a non-empty string")
            upper = method.strip().upper()
            if upper not in _HTTP_METHODS:
                allowed = ", ".join(sorted(_HTTP_METHODS))
                raise ValueError(f"route method '{method}' must be one of: {allowed}")
            normalized.append(upper)
        return normalized

    @field_validator("auth_required", "session_required", mode="before")
    @classmethod
    def parse_auth_flags(cls, v: bool | str | None, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator("templates", "static_assets", mode="before")
    @classmethod
    def coerce_ref_lists(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_route(self) -> "RuntimeApplicationRoute":
        seen_params: set[tuple[str, str]] = set()
        for parameter in self.parameters:
            key = (str(parameter.location), parameter.name)
            if key in seen_params:
                raise ValueError(
                    f"Duplicate runtime application parameter '{parameter.name}' "
                    f"in location '{parameter.location}' on route '{self.route_id}'"
                )
            seen_params.add(key)

        for field_name in ("templates", "static_assets"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate runtime application {field_name} entry on route '{self.route_id}'")
        return self


class RuntimeApplicationSurface(SDLModel):
    """An observed application surface hosted by a transport service on a node.

    ``service`` references the owning same-node ``Node.services[].name`` (bare
    name or the qualified ``nodes.<node>.services.<name>`` form). The surface is
    observation metadata; it never mutates ``Node.services``.
    """

    application_id: str
    service: str = ""
    protocol: RuntimeApplicationProtocol | str = RuntimeApplicationProtocol.HTTP
    name: str = ""
    base_path: str = ""
    framework: str = ""
    description: str = ""
    routes: list[RuntimeApplicationRoute] = Field(default_factory=list)

    @field_validator("application_id")
    @classmethod
    def validate_application_id(cls, v: str) -> str:
        return _require_symbol(v, field_name="application_id")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(
        cls,
        v: RuntimeApplicationProtocol | str,
    ) -> RuntimeApplicationProtocol | str:
        return parse_runtime_enum_or_var(v, RuntimeApplicationProtocol, field_name="protocol")

    @field_validator("base_path")
    @classmethod
    def validate_base_path(cls, v: str) -> str:
        return _url_path_or_var(v, field_name="base_path", allow_empty=True)

    @model_validator(mode="after")
    def validate_surface(self) -> "RuntimeApplicationSurface":
        seen_route_ids: set[str] = set()
        seen_method_paths: set[tuple[str, str]] = set()
        for route in self.routes:
            if route.route_id in seen_route_ids:
                raise ValueError(
                    f"Duplicate runtime application route_id '{route.route_id}' in application '{self.application_id}'"
                )
            seen_route_ids.add(route.route_id)
            for method in route.methods:
                if is_variable_ref(method) or is_variable_ref(route.path):
                    continue
                key = (method, route.path)
                if key in seen_method_paths:
                    raise ValueError(
                        f"Duplicate runtime application route binding "
                        f"'{method} {route.path}' in application '{self.application_id}'"
                    )
                seen_method_paths.add(key)
        return self


class RelationshipProxyUpstream(SDLModel):
    """Typed proxy-upstream detail carried by a top-level relationship edge.

    When a reverse proxy / gateway forwards a route to an upstream origin, the
    relationship's ``target`` resolves to that origin and this block keeps the
    forwarding facts structurally validated rather than recorded as prose:
    ``route_ref`` (a ``route_id`` on the proxy's application surface), the
    resolved upstream node/service, whether the client-facing TLS is terminated
    at the proxy, whether the proxy-to-origin hop is plaintext, and any request
    ``body_limit`` the proxy enforces.
    """

    route_ref: str
    upstream_node_ref: str = ""
    upstream_service_ref: str = ""
    client_tls_terminated: bool | str | None = None
    origin_plaintext: bool | str | None = None
    body_limit: str = ""
    description: str = ""

    @field_validator("route_ref")
    @classmethod
    def validate_route_ref(cls, v: str) -> str:
        # A reference, not a symbol definition: a ``${var}`` placeholder is
        # permitted, but an empty value is not.
        if not isinstance(v, str) or not v.strip():
            raise ValueError("route_ref must be a non-empty route_id")
        return v

    @field_validator("client_tls_terminated", "origin_plaintext", mode="before")
    @classmethod
    def parse_flags(cls, v: bool | str | None, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)
