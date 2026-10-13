"""Issue #1479: OCI imports through the distribution anonymous token flow.

ghcr.io, Docker Hub and ECR Public answer an anonymous registry request with
``401`` and ``WWW-Authenticate: Bearer realm=...,service=...,scope=...``. They
serve the token from an HTTPS realm and answer blob requests with ``307`` to a
storage host on another origin. These loopback servers reproduce that shape: a
registry that challenges until it receives the expected token, an HTTPS token
endpoint signed by a throwaway CA, and a storage origin that refuses, and
records, any request carrying ``Authorization``.
"""

from __future__ import annotations

import base64
import datetime as dt
import ipaddress
import json
import os
import ssl
import textwrap
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import raes.module_registry as module_registry
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from raes._errors import SDLParseError
from raes.module_registry import publish_module_to_oci_layout
from raes.parser import parse_sdl_file

REPOSITORY = "acme/shared"
SERVICE = "registry.test"
SCOPE = f"repository:{REPOSITORY}:pull"
TOKEN_QUERY = f"service={SERVICE}&scope=repository%3Aacme%2Fshared%3Apull"
SIGNED_QUERY = "X-Signature=storage-only"
MODULE = """
name: shared
version: 1.2.3
module:
  id: acme/shared
  version: 1.2.3
  exports:
    nodes: [vm]
    infrastructure: [vm]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
infrastructure:
  vm: 1
"""

Response = tuple[int, list[tuple[str, str]], bytes]
Route = Callable[[str, str | None], Response]


@dataclass(frozen=True)
class _Seen:
    path: str
    authorization: str | None


class _Handler(BaseHTTPRequestHandler):
    route: Route
    seen: list[_Seen]

    def do_GET(self) -> None:  # noqa: N802
        authorization = self.headers.get("Authorization")
        self.seen.append(_Seen(self.path, authorization))
        status, headers, body = self.route(self.path, authorization)
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


class _Server:
    """One loopback origin whose responses come from ``route``."""

    def __init__(self, route: Route, *, tls: ssl.SSLContext | None) -> None:
        self.seen: list[_Seen] = []
        handler = type("Handler", (_Handler,), {"route": staticmethod(route), "seen": self.seen})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        if tls is not None:
            self._server.socket = tls.wrap_socket(self._server.socket, server_side=True)
        scheme = "http" if tls is None else "https"
        self.origin = f"{scheme}://127.0.0.1:{self._server.server_address[1]}"
        # A short poll interval keeps shutdown fast; each test starts several servers.
        self._thread = threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@dataclass(frozen=True)
class _Layout:
    tag: str
    manifest_digest: str
    config_digest: str
    bundle_digest: str
    blobs: dict[str, bytes]


def _json(payload: object) -> Response:
    return 200, [("Content-Type", "application/json")], json.dumps(payload).encode("utf-8")


def _registry_route(
    layout: _Layout,
    *,
    token: str | None,
    challenges: list[str],
    blob_location: str = "",
    anonymous: bool = False,
) -> Route:
    """A registry that challenges until it sees ``token`` and redirects every blob.

    ``blob_location`` prefixes the ``307`` target: another origin, or "" for a
    same-origin path. ``/storage/`` paths on this origin behave like the storage
    host. ``token=None`` never accepts a token.
    """

    prefix = f"/v2/{REPOSITORY}/"
    storage = _storage_route(layout)

    def route(path: str, authorization: str | None) -> Response:
        if path.startswith("/storage/"):
            return storage(path, authorization)
        if not anonymous and (token is None or authorization != f"Bearer {token}"):
            headers = [("WWW-Authenticate", value) for value in challenges]
            return 401, [*headers, ("Content-Type", "application/json")], b'{"errors":[{"code":"UNAUTHORIZED"}]}'
        if path == f"{prefix}tags/list":
            return _json({"name": REPOSITORY, "tags": [layout.tag]})
        if path == f"{prefix}manifests/{layout.tag}":
            return 200, [("Content-Type", module_registry.OCI_LAYOUT_MEDIA_TYPE)], layout.blobs[layout.manifest_digest]
        if path.startswith(f"{prefix}blobs/"):
            digest = path.removeprefix(f"{prefix}blobs/")
            return 307, [("Location", f"{blob_location}/storage/{digest}?{SIGNED_QUERY}")], b""
        return 404, [], b""

    return route


def _storage_route(layout: _Layout) -> Route:
    """A blob storage host that refuses any request carrying ``Authorization``."""

    def route(path: str, authorization: str | None) -> Response:
        if authorization is not None:
            return 403, [], b"Authorization reached the storage origin"
        blob = layout.blobs.get(urlsplit(path).path.removeprefix("/storage/"))
        return (404, [], b"") if blob is None else (200, [], blob)

    return route


def _fixed_route(response: Response) -> Route:
    return lambda _path, _authorization: response


def _challenge(token_server: _Server, *, scope: str = SCOPE) -> str:
    return f'Bearer realm="{token_server.origin}/token",service="{SERVICE}",scope="{scope}"'


def _new_token() -> str:
    return base64.b64encode(os.urandom(24)).decode("ascii")


def _url(server: _Server, resource: str) -> str:
    return f"{server.origin}/v2/{REPOSITORY}/{resource}"


@pytest.fixture
def serve() -> Iterator[Callable[..., _Server]]:
    started: list[_Server] = []

    def start(route: Route, *, tls: ssl.SSLContext | None = None) -> _Server:
        server = _Server(route, tls=tls)
        started.append(server)
        return server

    yield start
    for server in started:
        server.close()


def _certificate(
    subject: x509.Name, issuer: x509.Name, key: ec.EllipticCurvePrivateKey, signer: ec.EllipticCurvePrivateKey
) -> x509.CertificateBuilder:
    now = dt.datetime.now(dt.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(hours=1))
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()),
            critical=False,
        )
    )


@pytest.fixture(scope="module")
def tls_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Path]:
    """A throwaway CA and a 127.0.0.1 leaf that pass Python's strict X.509 checks."""

    ca_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "issue 1479 test CA")])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    ca = (
        _certificate(ca_name, ca_name, ca_key, ca_key)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        _certificate(leaf_name, ca_name, leaf_key, ca_key)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    directory = tmp_path_factory.mktemp("issue-1479-tls")
    paths = (directory / "ca.pem", directory / "leaf.pem", directory / "leaf-key.pem")
    paths[0].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    paths[2].write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    return paths


@pytest.fixture
def https(tls_files: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> ssl.SSLContext:
    """Server context for the token endpoint; the client trusts the CA through ``SSL_CERT_FILE``."""

    ca_path, cert_path, key_path = tls_files
    monkeypatch.setenv("SSL_CERT_FILE", str(ca_path))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_path, key_path)
    return context


@pytest.fixture
def layout(tmp_path: Path) -> _Layout:
    module = tmp_path / "module" / "shared.yaml"
    module.parent.mkdir()
    module.write_text(MODULE.lstrip(), encoding="utf-8")
    layout_dir = Path(publish_module_to_oci_layout(module, output_dir=tmp_path / "dist")["layout_dir"])
    entry = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))["manifests"][0]
    blobs = {f"sha256:{blob.name}": blob.read_bytes() for blob in (layout_dir / "blobs" / "sha256").iterdir()}
    manifest = json.loads(blobs[entry["digest"]])
    return _Layout(
        tag=entry["annotations"]["org.opencontainers.image.ref.name"],
        manifest_digest=entry["digest"],
        config_digest=manifest["config"]["digest"],
        bundle_digest=manifest["layers"][0]["digest"],
        blobs=blobs,
    )


def _import_root(directory: Path, registry: _Server) -> Path:
    host = urlsplit(registry.origin).netloc
    (directory / "raes-trust.yaml").write_text(
        textwrap.dedent(
            f"""
            schema_version: raes-trust/v1
            registries:
              "{host}":
                require_signatures: false
                allow_insecure_http: true
            """
        ).lstrip(),
        encoding="utf-8",
    )
    root = directory / "root.yaml"
    root.write_text(
        textwrap.dedent(
            f"""
            name: root
            imports:
              - source: oci:{host}/{REPOSITORY}
                namespace: shared
                version: 1.2.3
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize("imports", [1, 2], ids=["one-import", "two-imports"])
def test_import_uses_one_anonymous_token_and_retries_each_request_once(
    tmp_path: Path, layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext, imports: int
) -> None:
    token = _new_token()
    token_server = serve(_fixed_route(_json({"token": token})), tls=https)
    storage = serve(_storage_route(layout))
    registry = serve(
        _registry_route(layout, token=token, challenges=[_challenge(token_server)], blob_location=storage.origin)
    )
    root = _import_root(tmp_path, registry)

    scenarios = [parse_sdl_file(root) for _ in range(imports)]

    assert [set(scenario.nodes) for scenario in scenarios] == imports * [{"shared.vm"}]
    # The token cache lives for one import resolution, so each import requests its own token.
    assert token_server.seen == imports * [_Seen(f"/token?{TOKEN_QUERY}", None)]
    resources = [
        f"/v2/{REPOSITORY}/tags/list",
        f"/v2/{REPOSITORY}/manifests/{layout.tag}",
        f"/v2/{REPOSITORY}/blobs/{layout.config_digest}",
        f"/v2/{REPOSITORY}/blobs/{layout.bundle_digest}",
    ]
    assert registry.seen == imports * [
        attempt for path in resources for attempt in (_Seen(path, None), _Seen(path, f"Bearer {token}"))
    ]
    assert storage.seen == imports * [
        _Seen(f"/storage/{digest}?{SIGNED_QUERY}", None) for digest in (layout.config_digest, layout.bundle_digest)
    ]


@pytest.mark.parametrize("cross_origin", [True, False], ids=["storage-origin", "same-origin"])
def test_bearer_token_never_follows_a_blob_redirect(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext, cross_origin: bool
) -> None:
    token = _new_token()
    token_server = serve(_fixed_route(_json({"token": token})), tls=https)
    storage = serve(_storage_route(layout))
    registry = serve(
        _registry_route(
            layout,
            token=token,
            challenges=[_challenge(token_server)],
            blob_location=storage.origin if cross_origin else "",
        )
    )

    payload = module_registry._bytes_request(_url(registry, f"blobs/{layout.bundle_digest}"))

    assert payload == layout.blobs[layout.bundle_digest]
    target = storage if cross_origin else registry
    redirected = [seen for seen in target.seen if seen.path.startswith("/storage/")]
    assert redirected == [_Seen(f"/storage/{layout.bundle_digest}?{SIGNED_QUERY}", None)]


def test_rejected_token_gets_exactly_one_retry(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext
) -> None:
    token_server = serve(_fixed_route(_json({"token": _new_token()})), tls=https)
    registry = serve(_registry_route(layout, token=None, challenges=[_challenge(token_server)]))
    url = _url(registry, "tags/list")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request(url)

    assert str(exc_info.value) == f"Failed to fetch OCI metadata from {url}"
    assert [seen.authorization is None for seen in registry.seen] == [True, False]
    assert len(token_server.seen) == 1


@pytest.mark.parametrize("challenges", [[], ['Basic realm="registry.test"']], ids=["no-challenge", "basic-only"])
def test_401_without_a_bearer_challenge_keeps_the_existing_failure(
    layout: _Layout, serve: Callable[..., _Server], challenges: list[str]
) -> None:
    registry = serve(_registry_route(layout, token=None, challenges=challenges))
    url = _url(registry, "tags/list")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request(url)

    assert str(exc_info.value) == f"Failed to fetch OCI metadata from {url}"
    assert len(registry.seen) == 1


@pytest.mark.parametrize(
    ("templates", "message"),
    [
        pytest.param(
            ['Bearer realm="{https}/token",service="a"', 'Bearer realm="{https}/token",service="b"'],
            "answered 401 with a malformed Bearer challenge",
            id="two-bearer-challenges",
        ),
        pytest.param(
            ['Bearer realm="{https}/token",scope="repository:acme/shared:pull  extra"'],
            "answered 401 with a malformed Bearer challenge",
            id="empty-scope-entry",
        ),
        pytest.param(
            ['Bearer realm="{http}/token",service="registry.test"'],
            "names a token realm that is not an absolute https URL",
            id="cleartext-realm",
        ),
    ],
)
def test_unusable_challenges_fail_before_any_token_request(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext, templates: list[str], message: str
) -> None:
    token_server = serve(_fixed_route(_json({"token": _new_token()})), tls=https)
    cleartext = serve(_fixed_route(_json({"token": _new_token()})))
    challenges = [template.format(https=token_server.origin, http=cleartext.origin) for template in templates]
    registry = serve(_registry_route(layout, token=None, challenges=challenges))
    url = _url(registry, "tags/list")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request(url)

    assert str(exc_info.value) == f"OCI registry {url} {message}"
    assert token_server.seen == []
    assert cleartext.seen == []


def test_token_endpoint_redirect_is_not_followed(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext
) -> None:
    token = _new_token()

    def token_route(path: str, _authorization: str | None) -> Response:
        if path.startswith("/token"):
            return 302, [("Location", "/elsewhere")], b""
        return _json({"token": token})

    token_server = serve(token_route, tls=https)
    registry = serve(_registry_route(layout, token=token, challenges=[_challenge(token_server)]))
    url = _url(registry, "tags/list")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request(url)

    assert str(exc_info.value) == f"Failed to obtain an anonymous OCI registry token for {url}"
    assert [urlsplit(seen.path).path for seen in token_server.seen] == ["/token"]
    assert len(registry.seen) == 1


@pytest.mark.parametrize(
    ("response", "message"),
    [
        pytest.param((500, [], b"{}"), "Failed to obtain an anonymous OCI registry token for {url}", id="status-500"),
        pytest.param(
            (200, [], b"<html>"), "OCI registry token response for {url} is not valid UTF-8 JSON", id="not-json"
        ),
        pytest.param((200, [], b"[]"), "OCI registry token response for {url} must be a JSON object", id="not-object"),
        pytest.param(_json({}), "OCI registry token response for {url} carries no usable bearer token", id="no-token"),
        pytest.param(
            _json({"token": 7}), "OCI registry token response for {url} carries no usable bearer token", id="number"
        ),
        pytest.param(
            _json({"token": "two words"}),
            "OCI registry token response for {url} carries no usable bearer token",
            id="space",
        ),
        pytest.param(
            _json({"token": "abc\r\nX-Injected: 1"}),
            "OCI registry token response for {url} carries no usable bearer token",
            id="header-injection",
        ),
    ],
)
def test_unusable_token_responses_fail_without_a_retry(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext, response: Response, message: str
) -> None:
    token_server = serve(_fixed_route(response), tls=https)
    registry = serve(_registry_route(layout, token=_new_token(), challenges=[_challenge(token_server)]))
    url = _url(registry, "tags/list")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request(url)

    assert str(exc_info.value) == message.format(url=url)
    assert len(registry.seen) == 1
    assert len(token_server.seen) == 1


def test_token_response_is_read_under_the_metadata_limit(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _new_token()
    response = _json({"token": token, "padding": "x" * 64})
    token_server = serve(_fixed_route(response), tls=https)
    registry = serve(_registry_route(layout, token=token, challenges=[_challenge(token_server)]))
    limits = replace(module_registry._OCI_LIMITS, max_metadata_bytes=64)
    monkeypatch.setattr(module_registry, "_OCI_LIMITS", limits)

    url = _url(registry, "tags/list")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request(url)

    # The message names the requested URL, not the token URL built from the challenge.
    assert str(exc_info.value) == (
        f"OCI response from {url} declares Content-Length {len(response[2])} bytes, exceeding the 64-byte limit"
    )
    assert len(registry.seen) == 1


@pytest.mark.parametrize(
    "body",
    [{"access_token": "{token}", "expires_in": 300}, {"token": "{token}", "access_token": "other"}],
    ids=["access-token-only", "token-preferred"],
)
def test_token_or_access_token_authorizes_the_retry(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext, body: dict[str, object]
) -> None:
    token = _new_token()
    filled = {key: value.format(token=token) if isinstance(value, str) else value for key, value in body.items()}
    token_server = serve(_fixed_route(_json(filled)), tls=https)
    registry = serve(_registry_route(layout, token=token, challenges=[_challenge(token_server)]))

    assert module_registry._json_request(_url(registry, "tags/list")) == {"name": REPOSITORY, "tags": [layout.tag]}
    assert registry.seen[-1].authorization == f"Bearer {token}"


def test_challenge_from_a_redirect_target_is_not_answered(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext
) -> None:
    token_server = serve(_fixed_route(_json({"token": _new_token()})), tls=https)
    storage = serve(_fixed_route((401, [("WWW-Authenticate", _challenge(token_server))], b"")))
    registry = serve(_registry_route(layout, token=None, challenges=[], blob_location=storage.origin, anonymous=True))
    url = _url(registry, f"blobs/{layout.bundle_digest}")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._bytes_request(url)

    assert str(exc_info.value) == f"Failed to fetch OCI blob from {url}"
    assert token_server.seen == []


def test_tokens_are_cached_per_challenge_for_one_resolution(
    layout: _Layout, serve: Callable[..., _Server], https: ssl.SSLContext
) -> None:
    token = _new_token()
    token_server = serve(_fixed_route(_json({"token": token})), tls=https)
    registry = serve(_registry_route(layout, token=token, challenges=[_challenge(token_server)]))
    url = _url(registry, "tags/list")
    tokens = module_registry._registry_auth._RegistryTokens()

    module_registry._json_request(url, tokens=tokens)
    module_registry._bytes_request(url, tokens=tokens)
    assert len(token_server.seen) == 1

    other_scope = module_registry._registry_auth._parse_bearer_challenge(
        _challenge(token_server, scope="repository:acme/other:pull")
    )
    assert tokens.token_for(other_scope, url=url) == token
    assert len(token_server.seen) == 2

    module_registry._json_request(url)
    assert len(token_server.seen) == 3


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param(
            'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:oras-project/oras:pull"',
            ("https://ghcr.io/token", "ghcr.io", "repository:oras-project/oras:pull"),
            id="ghcr",
        ),
        pytest.param(
            'Bearer realm="https://public.ecr.aws/token/",service="public.ecr.aws",scope="aws"',
            ("https://public.ecr.aws/token/", "public.ecr.aws", "aws"),
            id="ecr-public",
        ),
        pytest.param(
            '  bearer REALM="https://auth.test/token" , Service=registry.test  ',
            ("https://auth.test/token", "registry.test", None),
            id="case-and-whitespace",
        ),
        pytest.param(
            'Bearer realm="https://auth.test/token",service="say \\"hi\\"",error="insufficient_scope",x=1',
            ("https://auth.test/token", 'say "hi"', None),
            id="escapes-and-other-parameters",
        ),
    ],
)
def test_bearer_challenge_grammar_accepts_rfc_9110_parameters(
    header: str, expected: tuple[str, str | None, str | None]
) -> None:
    challenge = module_registry._registry_auth._parse_bearer_challenge(header)

    assert challenge == module_registry._registry_auth._BearerChallenge(*expected)


@pytest.mark.parametrize(
    "header",
    [
        "Bearer",
        "Bearer realm",
        "Bearer realm=",
        "Bearer abc==",
        'Bearer realm="https://auth.test/token",',
        'Bearer realm="https://auth.test/token",,service="registry.test"',
        'Bearer realm="https://auth.test/token" service="registry.test"',
        'Bearer realm="https://auth.test/token",REALM="https://auth.test/other"',
        'Bearer service="registry.test"',
        'Bearer realm="https://auth.test/token',
        'Bearer realm="https://auth.test/töken"',
        'Bearer realm="https://auth.test/token",scope="a  b"',
        'Bearer realm="https://auth.test/token",scope=""',
        'Basic realm="registry.test"',
    ],
)
def test_bearer_challenge_grammar_rejects_malformed_challenges(header: str) -> None:
    with pytest.raises(ValueError, match="malformed Bearer challenge"):
        module_registry._registry_auth._parse_bearer_challenge(header)


@pytest.mark.parametrize(
    ("realm", "accepted"),
    [
        ("https://auth.test/token", True),
        ("https://auth.test:8443/token?account=reader", True),
        ("HTTPS://auth.test/token", True),
        ("ftp://auth.test/token", False),
        ("https:///token", False),
        ("/token", False),
        ("https://reader@auth.test/token", False),
        ("https://auth.test/token#part", False),
        ("https://auth.test:99999/token", False),
        ("https://auth.test/a b", False),
        ("https://[::1/token", False),
        # urllib percent-decodes the host it connects to, and the socket layer IDNA-encodes it.
        ("https://a%20b.test/token", False),
        ("https://a%0a.test/token", False),
        ("https://a..test/token", False),
        (f"https://{'a' * 64}.test/token", False),
    ],
)
def test_token_realm_must_be_an_absolute_https_url(realm: str, accepted: bool) -> None:
    assert module_registry._registry_auth._is_https_url(realm) is accepted


def test_token_url_carries_the_service_and_each_scope_entry() -> None:
    challenge = module_registry._registry_auth._BearerChallenge(
        realm="https://auth.test/token?account=reader",
        service="registry.test",
        scope="repository:acme/shared:pull repository:acme/other:pull",
    )

    assert challenge.token_url() == (
        "https://auth.test/token?account=reader&service=registry.test"
        "&scope=repository%3Aacme%2Fshared%3Apull&scope=repository%3Aacme%2Fother%3Apull"
    )
    assert module_registry._registry_auth._BearerChallenge("https://auth.test/token", None, None).token_url() == (
        "https://auth.test/token"
    )
