"""Reference requests and outcomes for the Go input primitives (issue #1779)."""

from __future__ import annotations

import json
from collections.abc import Iterator

from raes_contracts import addressing, json_ingress, json_pointer, uri_safety


def primitive_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    """Record the four input primitives, including earlier ingress/pointer defects."""

    def case(command: str, name: str, request: dict[str, object]) -> tuple[str, str, dict[str, object]]:
        return command, name, request

    texts = [
        "[]",
        '{"event":1}',
        "[1e100]",
        "[5e-324]",
        "[1e-400]",
        "[-0.0]",
        "",
        " \t\n",
        "\v\f",
        "[",
        "[1] 2",
        "[01]",
        "[1.]",
        "[1e+]",
        "[true,false,null]",
        r'["a\\b\n\t\u0000\ud83d\ude00"]',
        '{"member":1,"member":2}',
        '{"member":NaN}',
        '{"member":1e999}',
        '{"member":-1e999}',
        '{"a":1,"a":2,"b":NaN}',
        '{"a":1,"a":2,"b":}',
        '{"a":{"b":1,"b":2},"c":NaN}',
        "[Infinity]",
        "[-Infinity]",
        "[" + "7" * 4300 + "]",
        "[-" + "7" * 4301 + "]",
        "[[]]",
        "[x[[[",
        r'["[\\\"[["]',
    ]
    for i, text in enumerate(texts):
        for root in ("array", "object"):
            for depth in (0, 1, 3):
                yield case(
                    "ingress",
                    f"ingress/{i}/{root}/{depth}",
                    {
                        "hex": text.encode().hex(),
                        "root": root,
                        "max_bytes": 10000,
                        "max_depth": depth,
                    },
                )
    for encoding in (
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
    ):
        for text in ('["é😀"]', "[]", '{"a":1,"a":2}'):
            yield case(
                "ingress",
                f"encoding/{encoding}/{text}",
                {
                    "hex": text.encode(encoding).hex(),
                    "root": "array",
                    "max_bytes": 1000,
                    "max_depth": 3,
                },
            )
    for i, data in enumerate((b'["\xff"]', b"\xff\xfe[\x00]", b"\x00\x00\xfe\xff\x00", b'["\x01"]')):
        yield case(
            "ingress",
            f"invalid-encoding/{i}",
            {
                "hex": data.hex(),
                "root": "array",
                "max_bytes": 100,
                "max_depth": 0,
            },
        )
    for size in (1, 2, 3):
        yield case(
            "ingress",
            f"byte-limit/{size}",
            {
                "hex": b"[]".hex(),
                "root": "array",
                "max_bytes": size,
                "max_depth": 0,
            },
        )
    uris = [
        "https://example.org/a",
        "https:",
        "https:///path",
        "http:/path",
        "//host/a",
        "/relative",
        "urn:isbn:0451450523",
        "mailto:a@b.c",
        "ftp://example.org/f",
        "data:,x",
        "https://user@example.org/",
        "https://user:pw@example.org/",
        "https://@example.org/",
        "https://example.org/#frag",
        "https://example.org/#",
        "https://[::1]/",
        "https://[::1]:443/",
        "https://[1.2.3.4]/",
        "https://[v1.fe80::a]/",
        "https://[vz.x]/",
        "https://[::1/",
        "https://::1]/",
        "https://a[::1]/",
        "https://[::1]x/",
        "https://[fe80::1%25eth0]/",
        "https://[fe80::1%25a%25b]/",
        "https://ex℀ample.org/",
        "https://exämple.org/",
        "https://\ua7f1.example.org/",
        "\x00 https://example.org/",
        "ht\ttps://example.org/",
        "HTTPS://EXAMPLE.ORG/",
        "1http://host/",
    ]
    names = (
        "token",
        "API_KEY",
        "my_secret_value",
        "ſecret",
        "paßword",
        "to%6Ben",
        "to+ken",
        "x=1;token",
        "",
        "tok%ZZen",
        "%E2%80%8Btoken",
        "%FFtoken",
        "auth",
        "sig",
        "key",
        "api-key",
        "credential",
        "signature",
        "apikey",
        "access_token",
        "x",
        "%+1%_1",
    )
    uris.extend("https://example.org/?" + name + "=1" for name in names)
    for i, uri in enumerate(uris):
        for strict in (False, True):
            yield case("uri", f"uri/{i}/{strict}", {"uri": uri, "strict": strict})
    tokens = (
        "",
        "~",
        "/",
        "~0",
        "~1",
        "~01",
        "a/b~c",
        "//~~",
        "é~1/",
        "01",
        "-1",
        "１",
        "²",
        "0",
        "9",
        "10",
        "9" * 5000,
        "~2",
        "%2F",
        "a~",
        "foo",
        'k"l',
        "i\\j",
    )
    for i, token in enumerate(tokens):
        for length in (-1, 0, 1, 10):
            yield case("pointer", f"pointer/{i}/{length}", {"token": token, "length": length})
    for i, pointer in enumerate(("", "/", "//", "/a//b", "abc/def", "abc", "/a~1b/m~0n/~01")):
        yield case("tokens", f"tokens/{i}", {"pointer": pointer})
    addresses = (
        "a.b",
        "a",
        "a.b\n",
        "A.b",
        "a..b",
        "__private.a",
        "a.__private",
        "_a.b",
        "a." + "b" * 64,
        "a." + "b" * 65,
        ".a.b",
        "a.b.",
        "é.b",
        ".".join(["a"] * 1024),
        ".".join(["a"] * 1025),
        "sdl.",
        "sdl.a",
        "participant.behavior-specification.x.inject-delivery.y",
        "participant.behavior-specification..inject-delivery.y",
    )
    for i, value in enumerate(addresses):
        yield case("address", f"address/{i}", {"value": value})
    for i, parts in enumerate(([], ["a", "", "b"], ["a.b", "c"], ["A", "b"], [""], ["__private", "x"])):
        yield case("render", f"render/{i}", {"parts": parts})
    for domain in ("provisioning", "orchestration", "evaluation", "unknown", ""):
        yield case("plan-root", f"plan-root/{domain}", {"domain": domain})


def compatibility_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    """Keep reference outcomes visible for the explicitly approved differences."""
    for name, data in (
        ("escaped-high", rb'["\ud800"]'),
        ("escaped-low", rb'["\udc00"]'),
        ("broken-pair", rb'["\ud83dA"]'),
        ("encoded-surrogate", b'["\xed\xa0\x80"]'),
    ):
        yield (
            "ingress-exception",
            "compatibility/" + name,
            {
                "hex": data.hex(),
                "root": "array",
                "max_bytes": 100,
                "max_depth": 0,
                "decision": "maintainer-1822-2026-11-02",
                "go": {"code": "invalid-json"},
            },
        )
    yield (
        "ingress-exception",
        "compatibility/decoder-depth",
        {
            "hex": (b"[" * 65001 + b"]" * 65001).hex(),
            "root": "array",
            "max_bytes": 200000,
            "max_depth": 0,
            "verdict_only": True,
            "decision": "maintainer-1822-2026-11-02",
            "go": {"code": "input-too-deep"},
        },
    )


def run_primitive(command: str, request: dict[str, object]) -> dict[str, object]:
    """Call the unchanged reference; free-text errors are not parity data."""

    if command == "ingress-exception":
        return {"reference": run_primitive("ingress", request), "go": request["go"], "decision": request["decision"]}
    if command == "ingress":
        try:
            value = json_ingress.parse_bounded_json(
                bytes.fromhex(request["hex"]),
                max_bytes=request["max_bytes"],
                root=request["root"],
                max_depth=request["max_depth"] or None,
            )
        except json_ingress.StrictJsonIngressError as exc:
            return {"code": exc.code}
        if request.get("verdict_only"):
            return {"code": ""}
        return {"sorted": json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)}
    if command == "uri":
        try:
            uri_safety.validate_safe_absolute_uri(
                request["uri"],
                field_name="uri",
                forbidden_schemes=("data", "FTP") if request["strict"] else (),
                forbid_fragment=request["strict"],
            )
        except ValueError as exc:
            message = str(exc)
            for phrase, code in (
                ("absolute URI", "absolute"),
                ("forbidden URI scheme", "scheme"),
                ("credential userinfo", "credentials"),
                ("fragment", "fragment"),
                ("secret-bearing", "secret"),
            ):
                if phrase in message:
                    return {"code": code}
            return {"code": "invalid"}
        return {"code": ""}
    if command == "pointer":
        token = request["token"]
        return {
            "escape": json_pointer.escape_token(token),
            "unescape": json_pointer.unescape_token(token),
            "is_index": json_pointer.is_array_index_token(token),
            "index": json_pointer.array_index(token, request["length"]),
        }
    if command == "tokens":
        tokens = json_pointer.pointer_tokens(request["pointer"])
        return {
            "tokens": list(tokens),
            "pointer": json_pointer.pointer_from_tokens(tokens),
        }
    if command == "address":
        value = request["value"]
        try:
            addressing.require_compiled_address(value)
            valid = True
        except ValueError:
            valid = False
        return {
            "valid": valid,
            "temporal": addressing.is_compiler_owned_temporal_subject_address(value),
        }
    if command == "render":
        try:
            return {"value": addressing.render_compiled_address(*request["parts"])}
        except ValueError:
            return {"value": None}
    if command == "plan-root":
        return {"value": addressing.PLAN_ADDRESS_ROOT_BY_DOMAIN.get(request["domain"])}
    raise ValueError("unknown primitive command: " + command)
