"""Reference cases for the remaining shared primitives of issue #1779."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC
from itertools import chain
from typing import Annotated

from pydantic import TypeAdapter, ValidationError
from raes_contracts import bounded_domains, errors, graphs, operational_logging, software_versions, timestamps
from raes_contracts._base import ContractModel, PrefixedDigestString
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest, jsonable_fallback
from raes_contracts.realization_structure import (
    DOCUMENT_SCALAR,
    RealizationConstraintLimits,
    validate_realization_value,
)
from raes_contracts.secret_references import SecretReferenceId


class _DocumentFixture(ContractModel):
    body: Annotated[str, DOCUMENT_SCALAR]


def requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    """Combine deterministic boundary requests for each shared primitive."""
    return chain(
        _timestamp_requests(),
        _version_requests(),
        _domain_requests(),
        _graph_requests(),
        _value_requests(),
        _identity_requests(),
        _log_requests(),
    )


def _timestamp_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    texts = (
        "2024-01-01T00:00:00Z",
        "2024-01-01t00:00:00z",
        "2024-01-01T05:30:00.25+05:30",
        "2016-12-31T23:59:60Z",
        "2017-01-01T05:29:60+05:30",
        "1972-06-30T23:59:60.1234567Z",
        "2015-12-31T23:59:60Z",
        "2024-02-30T00:00:00Z",
        "2024-01-01 00:00:00Z",
        "2024-01-01",
        "20240101T123456,000006",
        "2024-W01",
        "2024W011",
        "2020-W53-7T12:34",
        "2024-01-01☃12",
        "2024-01-01T12:34:56.123456789",
        "2024-01-01T00:00:00-01:30",
        "2024-01-01T00:00:00+00:00:30.5",
        "2024-01-01T00:00:00+00:00:00.5",
        "2024-01-01T00:00:00+01:99",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:59:59-01:00",
        "",
        "0000-01-01",
        "2021-W53-1",
        "2024-W011",
        "2024-01-01T24:00",
        "2024-01-01T12:60",
        "2024-01-01T12:34:60",
        "2024-01-01T12:34.5",
        "2024-01-01T12:3456",
        "2024-01-01T12:34:56.",
        "2024-01-01T12:34:56.x",
        "2024-01-01T12:34:56+24:00",
        "2024-01-01T12:34:56+-01:00",
    )
    for mode in ("rfc3339", "utc", "offset", "assuming"):
        for index, text in enumerate(texts):
            yield "timestamp", f"timestamp/{mode}/{index:02}", {"mode": mode, "text": text}


def _version_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    versions = (
        ("numeric-triplet", "7.9.0", None, "7.10.0"),
        ("numeric-triplet", None, "7.10.0", "7.9.0"),
        ("numeric-triplet", "7.9.0", None, "7.9.0"),
        ("numeric-triplet", None, "7.10.0", "7.10.0"),
        ("numeric-triplet", "7.9.0", None, "7.10.0-1"),
        ("numeric-triplet", "1.0", None, "2.0.0"),
        ("debian", "1:1.0-2", None, "2:0.1-1"),
        ("debian", None, "1.0-1", "1.0~rc1-1"),
        ("debian", "1.0", "1.0-0", "1.0"),
        ("debian", "1.0", None, "1-"),
        ("debian", "1.0", None, "1::2"),  # NOSONAR -- Malformed Debian epoch fixture, never a network address.
        ("debian", "1.0", None, "1.0-💥"),
        ("debian", "1.0", None, "1.0\n"),
        ("debian", "9223372036854775808:1", None, "9223372036854775809:0"),
        ("debian", "1.999999999999999999999999999999", None, "1.1000000000000000000000000000000"),
        ("debian", "1.0a", None, "1.0+"),
        ("debian", "1.0~~", None, "1.0~"),
        ("rpm", "1.0-1", None, "1.0-2"),
        ("rpm", "2.0", "2.0.1", "2.0^20250611"),
        ("rpm", "9223372036854775808:1", None, "9223372036854775809:0"),
        ("rpm", "1.0", None, "1.0~rc1"),
        ("private-order", "a", "z", "m"),
        ("private-order", "é" * 256, None, "m"),
        ("private-order", "é" * 257, None, "m"),
    )
    for index, (relation, lower, upper, actual) in enumerate(versions):
        for closed in (False, True):
            yield (
                "version",
                f"version/{index:02}/{closed}",
                {
                    "relation": relation,
                    "lower": lower,
                    "upper": upper,
                    "actual": actual,
                    "closed": closed,
                },
            )
    for field, value in (("authority", "urn:private"), ("revision", "2"), ("digest", "sha256:" + "0" * 64)):
        yield (
            "version",
            f"version/identity/{field}",
            {
                "relation": "numeric-triplet",
                "lower": "1.0.0",
                "actual": "2.0.0",
                "closed": True,
                "mutation": {field: value},
            },
        )


def _domain_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    yield (
        "domain",
        "domain/overflow",
        {
            "descriptor": {"kind": "numeric-interval", "numeric_type": "number", "lower": 0, "upper": 1},
            "value": 10**400,
        },
    )
    domains = (
        ({"kind": "exact", "value": 1}, 1),
        ({"kind": "exact", "value": 1}, True),
        ({"kind": "exact", "value": 1}, 1.0),
        ({"kind": "exact", "value": 1.0}, 1),
        ({"kind": "enum", "values": [True, 1, 1.0]}, 1),
        ({"kind": "enum", "values": [1, 1]}, 1),
        ({"kind": "enum", "values": []}, 1),
        ({"kind": "boolean"}, True),
        ({"kind": "boolean", "value": False}, True),
        ({"kind": "boolean", "value": False}, False),
        ({"kind": "null"}, None),
        ({"kind": "null"}, False),
        ({"kind": "numeric-interval", "numeric_type": "integer", "lower": 0, "upper": 2}, 0),
        ({"kind": "numeric-interval", "numeric_type": "integer", "lower": 0, "upper": 2}, 1.0),
        ({"kind": "numeric-interval", "numeric_type": "number", "lower": 0, "upper": 2, "lower_closed": False}, 0),
        ({"kind": "numeric-interval", "numeric_type": "number", "lower": 0, "upper": 2}, 1.5),
        ({"kind": "numeric-interval", "numeric_type": "integer", "lower": 0.5, "upper": 2}, 1),
        ({"kind": "numeric-interval", "numeric_type": "number", "lower": 2, "upper": 1}, 1),
        ({"kind": "governed-reference", "authority": "urn:a", "allowed_refs": ["x"]}, "x"),
        ({"kind": "governed-reference", "authority": "urn:a", "allowed_refs": ["x", "x"]}, "x"),
        ({"kind": "record", "fields": {"a": "other"}}, {"a": 1}),
    )
    for index, (descriptor, value) in enumerate(domains):
        yield "domain", f"domain/{index:02}", {"descriptor": descriptor, "value": value}


def _graph_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    for index, graph in enumerate(
        (
            {},
            {"a": []},
            {"a": ["a"]},
            {"a": ["b"], "b": []},
            {"a": ["b", "b"], "b": []},
            {"a": ["b"], "b": ["a"], "c": [], "d": ["a"]},
            {"a": [], "c": [], "b": ["a"]},
            {"a": ["a"], "b": ["c"], "c": ["b"], "d": ["b"]},
        )
    ):
        for reverse in (False, True):
            yield "graph", f"graph/{index:02}/{reverse}", {"graph": graph, "reverse": reverse}


def _value_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    values = (
        {"value": {"b": 1.0, "a": "é"}},
        {"value": [True, None, 42]},
        {"value": [1], "limits": {"max_nodes": 1}},
        {"value": [1], "limits": {"max_operations": 1}},
        {"value": [[1]], "limits": {"max_depth": 1}},
        {"value": [1, 2], "limits": {"max_members": 1}},
        {"value": {"ab": 1}, "limits": {"max_scalar_bytes": 1}},
        {"value": "é", "limits": {"max_scalar_bytes": 1}},
        {"value": [True, False], "limits": {"max_total_scalar_bytes": 8}},
        {
            "value": {"body": "12345"},
            "document": True,
            "limits": {"max_scalar_bytes": 4, "max_document_scalar_bytes": 8, "max_total_scalar_bytes": 16},
        },
        {"value": {"body": "12345"}, "limits": {"max_scalar_bytes": 4}},
        {"value": None, "limits": {"max_depth": 0}},
        {"value": 1e16, "canonical": True},
        {"value": {"nested": [1.0, -0.0, 5e-324]}, "canonical": True},
    )
    for index, request in enumerate(values):
        yield "value", f"value/{index:02}", request
    yield "carrier", "value/unknown-carrier", {}


def _identity_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    for index, text in enumerate(
        ("", "a", "a0", "a.b-c_d", "A", "1a", "a.", "a..b", "a-_b", "é", "a" * 256, "a" * 257)
    ):
        yield "secret", f"secret/{index:02}", {"text": text}
    for name, size in (("sha256", 64), ("sha384", 96), ("sha512", 128), ("blake3", 64), ("md5", 32)):
        for offset in (-1, 0, 1):
            yield "digest", f"digest/{name}/{offset}", {"text": name + ":" + "F" * (size + offset)}


def _log_requests() -> Iterator[tuple[str, str, dict[str, object]]]:
    for index, text in enumerate(
        (
            "message",
            "\n\r\t\x00\x1f\x7f\u0085",
            "é\ufffd",
            "\u200e\u200f\u2028\u2029\u202a\u202e\u2066\u2069",
            "é" * 8193,
            "a" * 8191 + "\n",
        )
    ):
        yield "log", f"log/{index:02}", {"text": text}
    yield "fault", "fault/categories", {}
    yield "clock", "clock/injected", {"text": "2024-01-01T05:30:00+05:30"}


def run(command: str, request: dict[str, object]) -> dict[str, object]:
    """Run the unchanged Python reference, retaining governed differences."""
    runners = {
        "timestamp": _timestamp,
        "version": _version,
        "domain": _domain,
        "graph": _graph,
        "value": _value,
        "secret": _secret,
        "digest": _digest,
        "log": _log,
        "carrier": _carrier,
        "fault": _fault,
        "clock": _clock,
    }
    try:
        runner = runners[command]
    except KeyError as exc:
        raise ValueError("unknown shared primitive command") from exc
    return runner(request)


def _carrier(_request: dict[str, object]) -> dict[str, object]:
    return {
        "decision": "maintainer-1779-2026-10-31",
        "reference": jsonable_fallback(object()),
        "go": {"accepted": False},
    }


def _fault(_request: dict[str, object]) -> dict[str, object]:
    kinds = (
        errors.InvalidInputError,
        errors.ConflictError,
        errors.NotFoundError,
        errors.AuthorizationError,
        errors.OperationalError,
        errors.EvidenceIntegrityError,
    )
    return {
        "categories": [
            "invalid-input",
            "conflict",
            "not-found",
            "authorization",
            "operational",
            "evidence-integrity",
        ],
        "hierarchy": all(issubclass(kind, errors.RaesError) for kind in kinds),
    }


def _clock(request: dict[str, object]) -> dict[str, object]:
    instant = timestamps.parse_timestamp_assuming_utc(request["text"]).astimezone(UTC)
    return {"utc": timestamps.isoformat_z(instant)}


def _timestamp(request: dict[str, object]) -> dict[str, object]:
    parsers = {
        "rfc3339": lambda text: timestamps.parse_rfc3339_datetime("at", text),
        "utc": timestamps.parse_offset_timestamp_utc,
        "offset": lambda text: timestamps.parse_offset_datetime(text, "at"),
        "assuming": timestamps.parse_timestamp_assuming_utc,
    }
    try:
        value = parsers[request["mode"]](request["text"])
    except ValueError as exc:
        return {"ok": False, "code": "leap" if "leap-second instant" in str(exc) else "invalid"}
    return {"ok": True, "text": timestamps.isoformat_z(value)}


def _version(request: dict[str, object]) -> dict[str, object]:
    name = request["relation"]
    identity = {
        "authority": "https://openrae.org/semantics/versions",
        "contract_id": name,
        "revision": "1",
        "digest": canonical_json_digest({"relation": name, "revision": "1"}),
    }
    identity.update(request.get("mutation", {}))
    try:
        domain = software_versions.VersionDomain(
            relation=identity,
            lower=request.get("lower"),
            upper=request.get("upper"),
            lower_closed=request.get("closed", True),
            upper_closed=request.get("closed", True),
        )
    except ValidationError:
        return {"valid": False}
    return {"valid": True, "membership": software_versions.version_membership(request["actual"], domain)}


def _domain(request: dict[str, object]) -> dict[str, object]:
    try:
        descriptor = TypeAdapter(bounded_domains.NullableDomainDescriptor).validate_python(request["descriptor"])
    except ValidationError:
        return {"valid": False}
    try:
        member = bounded_domains.scalar_in_domain(request["value"], descriptor)
    except OverflowError:
        return {"valid": True, "refusal": "numeric-overflow"}
    return {"valid": True, "member": member}


def _graph(request: dict[str, object]) -> dict[str, object]:
    key = (lambda name: tuple(-ord(character) for character in name)) if request["reverse"] else (lambda name: name)
    graph = request["graph"]
    return {
        "cycle": graphs.has_cycle(graph),
        "order": graphs.stable_topological_order(graph, key=key),
        "components": [list(component) for component in graphs.cyclic_components(graph, key=key)],
    }


def _value(request: dict[str, object]) -> dict[str, object]:
    try:
        limits = RealizationConstraintLimits(**request.get("limits", {}))
    except ValidationError:
        return {"status": "invalid-limits"}
    payload = request["value"]
    if request.get("document"):
        payload = _DocumentFixture.model_validate(payload)
    result = validate_realization_value(payload, limits=limits, python_carriers=bool(request.get("document")))
    if not request.get("canonical") or not result.conformant:
        return {"status": result.status.value}
    return _canonical_value(payload)


def _canonical_value(payload: object) -> dict[str, object]:
    try:
        encoded = canonical_json_bytes(payload).decode()
    except ValueError, TypeError:
        return {"status": "invalid"}
    return {"status": "conformant", "canonical": encoded}


def _secret(request: dict[str, object]) -> dict[str, object]:
    try:
        TypeAdapter(SecretReferenceId).validate_python(request["text"])
    except ValidationError:
        return {"valid": False}
    return {"valid": True}


def _digest(request: dict[str, object]) -> dict[str, object]:
    try:
        TypeAdapter(PrefixedDigestString).validate_python(request["text"])
    except ValidationError:
        return {"valid": False}
    return {"valid": True}


def _log(request: dict[str, object]) -> dict[str, object]:
    record = logging.LogRecord("parity", logging.WARNING, "", 0, request["text"], (), None)
    return {"text": operational_logging.ValueFreeFormatter(fmt="%(message)s").format(record)}
