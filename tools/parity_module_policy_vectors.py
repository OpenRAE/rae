#!/usr/bin/env python3
"""Record workspace-policy and version-request behavior from the Python owner."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))
from packaging.specifiers import InvalidSpecifier  # noqa: E402
from raes._errors import SDLError  # noqa: E402
from raes.module_registry._digests import _normalize_exact_or_range, _satisfies_version  # noqa: E402
from raes.module_registry.models import load_trust_policy  # noqa: E402


def policy_inputs() -> list[str]:
    scalars = [
        "yes",
        "NO",
        "on",
        "Off",
        "true",
        "FALSE",
        "0",
        "1",
        "-1",
        "2",
        "0x1",
        "0b0",
        "01",
        "00",
        "1_0",
        "1:00",
        "0.0",
        "1.0",
        "2.5",
        "0:01.0",
        "-0.0",
        ".inf",
        ".NaN",
        "null",
        "~",
        "=",
        "'yes'",
        "'f'",
        "'n'",
        "'Y'",
        "'0'",
        "'bad'",
        "2001-12-15",
        "2001-12-15T02:59:43Z",
        "2001-12-15 2:59:43.1 -5:30",
        "2001-02-30",
        "2001-12-15T25:00:00Z",
        "2001-12-15T02:00:00+24:00",
        "[true]",
        "{}",
    ]
    rows = [
        "",
        "# empty\n",
        "{}",
        "[]",
        "null",
        "unknown: true",
        "schema_version: 1",
        "schema_version: 'custom'",
        "registries: []",
        "registries: {example: null}",
        "registries: {example: {unknown: false}}",
        "registries: {example: {trusted_signers: []}}",
        "registries: {example: {trusted_signers: {test: 12}}}",
        "registries: {example: {trusted_signers: {test: 'public-test-key'}}}",
    ]
    rows += ["allow_unsigned_local_sources: " + value for value in scalars]
    rows += [
        "registries: {example: {require_signatures: " + value + ", allow_insecure_http: false}}" for value in scalars
    ]
    rows += [
        "allow_unsigned_local_sources: &flag false\n"
        "registries: {example: {require_signatures: *flag, allow_insecure_http: on}}",
        "registries:\n  example:\n    <<: [{require_signatures: false}, {allow_insecure_http: true}]\n"
        "    trusted_signers: {test: key}\n",
        "registries: {example: {<<: 7}}",
        "registries: {example: {<<: [7]}}",
        "registries: {example: &self {<<: *self, require_signatures: true}}",
        "{1: true}",
        "{[a, b]: true}",
        "{'<<': true}",
        "allow_unsigned_local_sources: [*missing]",
    ]
    return rows


def verify_reference_sources() -> None:
    reference_sources = {
        "_digests.py": "9ceeddbda9f288695a588a0c86b9061bd4578a45e097d5c454af85a926bdedb2",
        "models.py": "6afcd65ef2ea5be50017f0412aa6a83d6b48726d02d2553d0b00ac74df451218",
    }
    reference_dir = ROOT / "implementations/python/packages/raes/module_registry"
    for source, expected in reference_sources.items():
        if hashlib.sha256((reference_dir / source).read_bytes()).hexdigest() != expected:
            raise ValueError("Module policy reference source differs from its pinned contents")


def policy_cases() -> list[dict[str, Any]]:
    policies = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "raes-trust.yaml"
        for source in policy_inputs():
            path.write_text(source)
            row = {"source": source}
            try:
                policy = load_trust_policy(Path(directory))
            except SDLError:
                row["accepted"] = False
            else:
                row.update(
                    accepted=True,
                    expected={
                        "SchemaVersion": policy.schema_version,
                        "AllowUnsignedLocalSources": policy.allow_unsigned_local_sources,
                        "Registries": {
                            key: {
                                "RequireSignatures": rule.require_signatures,
                                "AllowInsecureHTTP": rule.allow_insecure_http,
                                "TrustedSigners": rule.trusted_signers,
                            }
                            for key, rule in policy.registries.items()
                        },
                    },
                )
            policies.append(row)
    return policies


def version_cases() -> list[dict[str, Any]]:
    actuals = [
        "invalid",
        "0",
        "0.9",
        "1",
        "1.0",
        "1.0.0",
        "1.0a1",
        "1.0b2",
        "1.0rc1",
        "1.0.dev1",
        "1.0.post1",
        "1.0.post2.dev3",
        "1.0+abc",
        "1.0+abc.1",
        "1.0+abc.2",
        "1.0+1",
        "1.0+2",
        "1.0+01.a",
        "1.0+1.b",
        "1.0+abc.def",
        "1.1",
        "2.0",
        "2!1.0",
        "1!1.0",
        "v01.02-alpha_2",
        "1.0preview",
        "1.0rev",
        "1.0-2",
        "1.0.dev0",
        "0.1dev1",
        "2.0rc1",
    ]
    requests = [
        "",
        "*",
        "1.0",
        "==1.0",
        "!=1.0",
        "==1.*",
        "!=1.*",
        ">=1.0",
        "<=1.0",
        ">1.0",
        "<1.0",
        "~=1.0",
        "~=1.0.0",
        ">=1.0a1",
        "<1.0rc2",
        ">1.0.post1",
        ">=1.0.dev0",
        "==1.0+abc",
        "==1!1.0",
        ">=1!1.0",
        "===1.0+ABC",
        "==1.0.*,!=1.0.post1",
        ">=1,<2",
        "~=1",
        ">=1.*",
        "==1.0a1.*",
        ">=1+abc",
        "invalid",
        "===bad value",
        ",",
        "==",
        "==1.0,",
        "<=2.0rc1",
    ]
    versions = []
    for request in requests:
        try:
            _normalize_exact_or_range(request)
        except InvalidSpecifier:
            versions.append({"request": request, "valid": False})
            continue
        for actual in actuals:
            versions.append(
                {
                    "request": request,
                    "actual": actual,
                    "valid": True,
                    "accepted": _satisfies_version(actual, request),
                }
            )
    return versions


def record() -> dict[str, list[dict[str, Any]]]:
    verify_reference_sources()
    return {"policies": policy_cases(), "versions": version_cases()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "implementations/go/sdl/module/testdata/policy-versions.json"
    encoded = json.dumps(record(), indent=2) + "\n"
    if args.check:
        return int(path.read_text() != encoded)
    path.write_text(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
