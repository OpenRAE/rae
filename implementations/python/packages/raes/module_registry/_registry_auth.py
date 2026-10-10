"""OCI distribution anonymous bearer-token flow for module-registry fetches.

Public registries such as ghcr.io, Docker Hub and ECR Public answer an anonymous
``/v2/`` request with ``401`` and a ``WWW-Authenticate: Bearer`` challenge. The
distribution token specification has the client request a token from the
challenge ``realm`` with its ``service`` and ``scope``, then repeat the request
with ``Authorization: Bearer <token>`` (issue #1479).

The flow is anonymous: no credential is read, stored or sent, and the token
request follows no redirect. The token rides only on the single retry of the
challenged request, as an unredirected header, so urllib never copies it into
a redirected request. Registries answer blob requests with a ``307`` to a
storage origin, which must not receive it.
"""

from __future__ import annotations

import re
from contextlib import closing
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPDefaultErrorHandler,
    HTTPErrorProcessor,
    HTTPSHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    UnknownHandler,
)

from .._errors import SDLParseError

# RFC 9110 token and quoted-string (section 5.6), restricted to ASCII.
_TCHARS = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
_QUOTED_STRING = r'"(?:[\t \x21\x23-\x5b\x5d-\x7e]|\\[\t \x21-\x7e])*"'
_SCHEME = re.compile(rf"({_TCHARS})(?: +|$)")
_AUTH_PARAM = re.compile(rf"({_TCHARS})[ \t]*=[ \t]*({_TCHARS}|{_QUOTED_STRING})")
_LIST_SEPARATOR = re.compile(r"[ \t]*,[ \t]*")
_QUOTED_PAIR = re.compile(r"\\(.)")
# RFC 6749 scope-token. RFC 6750 b64token is the bearer credential syntax, so a token
# that matches it cannot carry header text.
_SCOPE_TOKEN = re.compile(r"[\x21\x23-\x5b\x5d-\x7e]+")
_B64TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*")
_URL_TEXT = re.compile(r"[\x21-\x7e]+")
_MALFORMED = "malformed Bearer challenge"


@dataclass(frozen=True)
class _BearerChallenge:
    """The parameters a token request needs; also the token cache key."""

    realm: str
    service: str | None
    scope: str | None

    def token_url(self) -> str:
        """Return the realm with ``service`` and each space-delimited scope entry as query parameters."""

        query = [] if self.service is None else [("service", self.service)]
        query.extend(("scope", entry) for entry in ([] if self.scope is None else self.scope.split(" ")))
        parts = urlsplit(self.realm)
        joined = "&".join(part for part in (parts.query, urlencode(query)) if part)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, joined, ""))


def _unquoted(value: str) -> str:
    return _QUOTED_PAIR.sub(r"\1", value[1:-1]) if value.startswith('"') else value


def _auth_params(text: str, position: int) -> dict[str, str]:
    """Return the comma-separated auth-params from ``position`` to the end of ``text``."""

    params: dict[str, str] = {}
    while True:
        param = _AUTH_PARAM.match(text, position)
        if param is None or param.group(1).lower() in params:
            raise ValueError(_MALFORMED)
        params[param.group(1).lower()] = _unquoted(param.group(2))
        position = param.end()
        if position == len(text):
            return params
        separator = _LIST_SEPARATOR.match(text, position)
        if separator is None:
            raise ValueError(_MALFORMED)
        position = separator.end()


def _is_bearer(value: str) -> bool:
    scheme = _SCHEME.match(value.strip(" \t"))
    return scheme is not None and scheme.group(1).lower() == "bearer"


def _parse_bearer_challenge(value: str) -> _BearerChallenge:
    """Parse one ``Bearer`` challenge strictly (RFC 9110 sections 11.2-11.3, RFC 6750 section 3).

    ``realm`` is required and other parameters are ignored, as RFC 6750 allows.
    Anything else, including a duplicate parameter, fails with ``ValueError``.
    """

    text = value.strip(" \t")
    scheme = _SCHEME.match(text)
    if scheme is None or scheme.group(1).lower() != "bearer":
        raise ValueError(_MALFORMED)
    params = _auth_params(text, scheme.end())
    realm, scope = params.get("realm"), params.get("scope")
    if realm is None or (scope is not None and not all(_SCOPE_TOKEN.fullmatch(entry) for entry in scope.split(" "))):
        raise ValueError(_MALFORMED)
    return _BearerChallenge(realm=realm, service=params.get("service"), scope=scope)


def _is_https_url(url: str) -> bool:
    """Accept only an absolute ``https`` URL with a host and no userinfo, fragment or whitespace."""

    try:
        parts = urlsplit(url)
        # ``port`` raises ValueError when the port is out of range.
        port_valid = parts.port is None or parts.port > 0
    except ValueError:
        return False
    return all(
        (
            port_valid,
            _URL_TEXT.fullmatch(url) is not None,
            parts.scheme == "https",
            bool(parts.hostname),
            "@" not in parts.netloc,
            not parts.fragment,
        )
    )


def _challenge_for(error: HTTPError, request: Request) -> _BearerChallenge | None:
    """Return the Bearer challenge of a ``401`` from the requested URL itself, or ``None``."""

    url = request.full_url
    with closing(error):
        if error.code != 401 or error.url != url:
            return None
        bearer = [value for value in error.headers.get_all("WWW-Authenticate") or () if _is_bearer(value)]
    if not bearer:
        return None
    malformed = f"OCI registry {url} answered 401 with a {_MALFORMED}"
    if len(bearer) > 1:
        raise SDLParseError(malformed)
    try:
        challenge = _parse_bearer_challenge(bearer[0])
    except ValueError as exc:
        raise SDLParseError(malformed) from exc
    if not _is_https_url(challenge.realm):
        raise SDLParseError(f"OCI registry {url} names a token realm that is not an absolute https URL")
    return challenge


def _anonymous_token(challenge: _BearerChallenge, *, url: str) -> str:
    """Request an anonymous token from the challenge realm over HTTPS, following no redirect."""

    from . import _OCI_LIMITS, _decode_json_object, _read_capped

    token_url = challenge.token_url()
    # No HTTP, redirect, FTP, file or data handler: the validated HTTPS realm is the only hop.
    opener = OpenerDirector()
    for handler in (ProxyHandler(), UnknownHandler(), HTTPSHandler(), HTTPDefaultErrorHandler(), HTTPErrorProcessor()):
        opener.add_handler(handler)
    request = Request(token_url, headers={"Accept": "application/json"})  # noqa: S310 - validated https realm
    try:
        with opener.open(request, timeout=_OCI_LIMITS.timeout_seconds) as response:
            payload = _read_capped(response, url=token_url, max_bytes=_OCI_LIMITS.max_metadata_bytes)
    except URLError as exc:
        raise SDLParseError(f"Failed to obtain an anonymous OCI registry token for {url}") from exc
    document = _decode_json_object(payload, context=f"OCI registry token response for {url}")
    token = document.get("token") or document.get("access_token")
    if not isinstance(token, str) or _B64TOKEN.fullmatch(token) is None:
        raise SDLParseError(f"OCI registry token response for {url} carries no usable bearer token")
    return token


@dataclass
class _RegistryTokens:
    """Anonymous tokens for one import resolution, keyed by realm, service and scope."""

    _tokens: dict[_BearerChallenge, str] = field(default_factory=dict)

    def token_for(self, challenge: _BearerChallenge, *, url: str) -> str:
        if challenge not in self._tokens:
            self._tokens[challenge] = _anonymous_token(challenge, url=url)
        return self._tokens[challenge]


def _open_capped(request: Request, *, url: str, max_bytes: int) -> bytes:
    # ``urlopen`` and the limits resolve through the package facade, so its seams apply (issue #48).
    from . import _OCI_LIMITS, _read_capped, urlopen

    with urlopen(request, timeout=_OCI_LIMITS.timeout_seconds) as response:
        return _read_capped(response, url=url, max_bytes=max_bytes)


def _registry_get(
    url: str,
    *,
    headers: dict[str, str] | None,
    max_bytes: int,
    tokens: _RegistryTokens | None,
    failure: str,
) -> bytes:
    """GET ``url`` anonymously; answer one Bearer challenge with one token-bearing retry."""

    request = Request(url, headers=dict(headers or {}))  # noqa: S310 - trust-policy registry URL
    try:
        return _open_capped(request, url=url, max_bytes=max_bytes)
    except HTTPError as exc:
        challenge = _challenge_for(exc, request)
        if challenge is None:
            raise SDLParseError(failure) from exc
    except URLError as exc:
        raise SDLParseError(failure) from exc
    token = (_RegistryTokens() if tokens is None else tokens).token_for(challenge, url=url)
    retry = Request(url, headers=dict(headers or {}))  # noqa: S310 - trust-policy registry URL
    # Unredirected: urllib copies only ``Request.headers`` into a redirected request.
    retry.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        return _open_capped(retry, url=url, max_bytes=max_bytes)
    except URLError as exc:
        raise SDLParseError(failure) from exc
