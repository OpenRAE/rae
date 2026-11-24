#!/usr/bin/env python3
"""Record the source-layer oracle vectors for the Go decoder.

The Python implementation remains unchanged. This narrow recorder does not run
pytest or the full parity-corpus recorder. Use --check for a read-only comparison.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

import yaml
from raes import SDLParseError, SDLParserLimits, load_sdl_fragment
from raes._errors import SDLParseDiagnostic
from raes._mapping_scopes import MappingScope
from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from raes._source_profile import SDLSourceParseOptions
from raes._yaml_loader import SDLSourceLocations, load_sdl_yaml
from raes.parser import _normalize_keys

VALUE_PREFIX = "value: "
SIMPLE_SOURCE = "x: y\n"
DUPLICATE_SOURCE = "a: x\na: y\n"

OUTPUT = ROOT / "implementations/go/internal/sdl/source/testdata/reference.json"


def machine(diagnostic: SDLParseDiagnostic) -> dict[str, Any]:
    result = diagnostic.as_dict()
    result.pop("message", None)
    for related in result.get("related", []):
        related.pop("message", None)
    return result


def add_case(cases: list[dict[str, Any]], name: str, text: str, **kw: Any) -> None:
    options = {k: v for k, v in kw.items() if k != "limits"}
    limits = kw.get("limits", {})
    diagnostics = []
    try:
        value = load_sdl_fragment(text, limits=SDLParserLimits(**limits), source_diagnostics=diagnostics, **options)
        error = False
    except SDLParseError as exc:
        value = None
        error = True
        diagnostics = list(exc.diagnostics)
    cases.append(
        {
            "name": name,
            "source": text,
            "options": options,
            "limits": limits,
            "error": error,
            "value": value,
            "diagnostics": [machine(d) for d in diagnostics],
        }
    )


def scalar_cases(cases: list[dict[str, Any]]) -> None:
    for scalar in [
        "yes",
        "NO",
        "on",
        "Off",
        "true",
        "True",
        "TRUE",
        "false",
        "False",
        "FALSE",
        "null",
        "Null",
        "NULL",
        "~",
        "012",
        "0o12",
        "0x0a",
        "0b11",
        "-0x0a",
        "+0o12",
        "1_000",
        "2026-07-11",
        "1e3",
        "1.0e+2",
        "-.5",
        "+.5",
        "1.",
        "1.0",
        "+12",
        "-0",
        "0",
        "10:20",
        "1E-999",
        ".inf",
        "-.Inf",
        ".NaN",
        "1e309",
        "99999999999999999999999999999999999999",
        "'true'",
        '"yes"',
        '"\\u263A"',
        "'it''s fine'",
        "|\n  one\n  two\n",
        ">\n  one\n  two\n",
    ]:
        add_case(cases, "scalar-" + str(len(cases)), VALUE_PREFIX + scalar + "\n")


def profile_cases(cases: list[dict[str, Any]]) -> None:
    for text in [
        "Name: example\n",
        "name: example\nName: second\n",
        "a: 1\na: 2\nb: 1\nb: 2\n",
        "true: a\nnull: b\n1: c\n",
        "nodes: {web-app: {type: switch}, web_app: {type: switch}}\n",
        "nodes: {Web-App: {type: switch}}\n",
        "nodes: {a: {Type: switch, type: switch}}\n",
        "labels: {A-B: {Field-Name: text}}\n",
        "schema_document: {Type: string, Properties: {X-Y: {Type: string}}}\n",
        "profile_value: {a: {B-C: true}}\n",
        "a: &a {x: 1}\nb: {<<: *a}\n",
        "a: &a {x: 1}\nb: {<<: *a, x: 2}\n",
        "a: &a {x: 1}\nb: &b {x: 2}\nc: {<<: [*a, *b]}\n",
        "a: &a [*a]\n",
        "a: &a {self: *a}\n",
        "a: &a [1, 2]\nb: [*a, *a]\n",
        "value: !!str yes\n",
        "%YAML 1.2\n---\nvalue: yes\n",
        "---\nname: first\n---\nname: second\n",
        "\n# empty\n",
        "value: [\n",
        "name: x\nnodes: {a.b: {type: switch}}\n",
        "name: x\nmaterialization_provenance: {}\nnodes: {a.b: {type: switch}}\n",
    ]:
        for migration in ["reject", "accept"]:
            add_case(cases, "profile-" + str(len(cases)), text, migration_policy=migration)


def limit_cases(cases: list[dict[str, Any]]) -> None:
    for field, text, lower, exact in [
        ("max_input_bytes", SIMPLE_SOURCE, 4, 5),
        ("max_scalar_bytes", "x: four\n", 3, 4),
        ("max_depth", "x: {y: z}\n", 2, 3),
        ("max_nodes", SIMPLE_SOURCE, 2, 3),
        ("max_aliases", "a: &a z\nb: [*a, *a]\n", 1, 2),
        ("max_expanded_nodes", "a: &a [x, y]\nb: [*a, *a]\n", 12, 13),
    ]:
        for n in [lower, exact, exact + 1]:
            add_case(cases, "limit-" + field + "-" + str(n), text, limits={field: n})


def edge_cases(cases: list[dict[str, Any]]) -> None:
    for text in [
        "name: café\n",
        'name: "\\uD800"\n',
        'name: "line\\nfeed"\n',
        "a: [yes, 012, -0x0a, null]\n",
        'a: {"a/b": {"~x": 1, "~x": 2}}\n',
    ]:
        add_case(cases, "edge-" + str(len(cases)), text)

    for path in ["structural", "literal"]:
        add_case(cases, "scope-" + path, "A-B: {C-D: yes}\n", mapping_keys=path)

    add_case(cases, "base-pointer", DUPLICATE_SOURCE, base_pointer="/items/0")

    add_case(cases, "format-choice", SIMPLE_SOURCE, source_format="no")

    add_case(cases, "migration-choice", SIMPLE_SOURCE, migration_policy="no")


def dialect_cases(cases: list[dict[str, Any]]) -> None:
    for text in [
        "a: !!str test\n",
        "a: !custom test\n",
        "a: !<tag:yaml.org,2002:str> test\n",
        "a: [1, 2]\n---\nb: 3\n",
        "a: {b: c}\n...\n",
        "? [a, b]\n: c\n",
        "a:\n",
        "a: \n b: c\n",
        "a: {}\nb: []\n",
        "a: &x 1\nb: &x 2\n",
        "a: *missing\n",
        "a: 1\n  b: 2\n",
        "a:\n\tb: 1\n",
        'a: "bad\\q"\n',
        "a: 'bad\n",
        'a: "bad\n',
        "a: [one, two\n",
        "a: {one: two\n",
        "a: {one two}\n",
        "a: [one two]\n",
        "a: [x,]\n",
        "a: {x: 1,}\n",
        'a: "\\uD800\\uDC00"\n',
        'a: "\\U0000D800"\n',
        'a: "\\U0001F600"\n',
        'a: "\\x00"\n',
        "a: null\ntrue: .nan\n",
        "a: &a {x: .inf}\nb: *a\n",
        "a: &a [x]\nb:\n  c: *a\n",
        "a: |\n  one\n  two\nb: final\n",
        "a: |-\n  one\n  two\nb: final\n",
        "a: >-\n  one\n  two\nb: final\n",
        "a: |+\n  one\n\n\nb: final\n",
        "name: test\nnodes:\n  'true': {type: switch}\n",
        "labels: {A-B: {Field-Name: text}}\n",
        "properties: [{Property-Name: text}]\n",
        "a: &a {Field-Name: x}\nlabels: {Key: *a}\n",
        "a: &a {x: y}\nb: {<<: [*a, *a]}\n",
        "a: {<<: 2}\n",
        "a: &a {x: y}\nb: {<<: *a, <<: *a}\n",
    ]:
        for migration in ["reject", "accept"]:
            add_case(cases, "dialect-" + str(len(cases)), text, migration_policy=migration)


def presentation_cases(cases: list[dict[str, Any]]) -> None:
    for i, value in enumerate(
        [
            "",
            "yes",
            "No",
            "ON",
            "off",
            "null",
            "~",
            "012",
            "0o12",
            "0b10",
            "1_000",
            "1e3",
            "a:b",
            "a: b",
            "a # b",
            "-",
            "?",
            "---",
            "...",
            " leading",
            "trailing ",
            "one\ntwo",
            "\none",
            "one\n",
            "one\n\n\n",
            "one \ntwo",
            "one\n two",
            "one\n  two",
            " ".join(["word"] * 40),
            " ".join(["word"] * 15) + " it's a quote " + " ".join(["word"] * 20),
            "café " * 30,
            "😀" * 30,
            "a" * 100 + "é" + "b" * 50,
            "".join(
                chr(i)
                for i in [
                    0,
                    7,
                    8,
                    9,
                    11,
                    12,
                    13,
                    27,
                    133,
                    160,
                    8232,
                    8233,
                    127,
                    128,
                    255,
                ]
            ),
        ]
    ):
        add_case(
            cases,
            "presentation-" + str(i),
            json.dumps({"value": value}, ensure_ascii=True) + "\n",
        )


def retained_cases(cases: list[dict[str, Any]]) -> None:
    for length in [127, 128, 129, 130]:
        add_case(cases, "long-key-" + str(length), json.dumps({"x" * length: "value"}) + "\n")

    for text in [
        "[1, 2, [3, 4]]\n",
        "{a: [{b: c, d: {e: f}}, {g: [h, i]}]}\n",
        "a: &a\n  {x: y}\nb: *a\n",
        "materialization_provenance: {}\nnodes: {a.__private.b: {type: switch}}\n",
        "a: &a {B-C: x}\nx: {<<: *a}\n",
        DUPLICATE_SOURCE,
    ]:
        add_case(cases, "retained-" + str(len(cases)), text, migration_policy="accept")

    for f in RUNTIME_SERVICE_FAMILIES:
        for identity in ["valid", "Invalid"]:
            add_case(
                cases,
                "identity-" + f.collection_name + "-" + identity,
                json.dumps({"nodes": {"n": {"runtime": {f.collection_name: [{f.id_field: identity}]}}}}) + "\n",
            )


def boundary_cases(cases: list[dict[str, Any]]) -> None:
    for value in [
        "😀" * 30,
        "+-1",
        "-+1",
        "--1",
        "1e+-1",
        "1e-+1",
        "---hello",
        "...hello",
    ]:
        add_case(
            cases,
            "additional-" + str(len(cases)),
            json.dumps({"value": value}, ensure_ascii=False) + "\n",
        )

    for text in [
        "value: +-1\n",
        "value: 1e+-1\n",
        "value: 0o" + "7" * 4600 + "\n",
        VALUE_PREFIX + "9" * 4300 + "\n",
        VALUE_PREFIX + "9" * 4301 + "\n",
        "x: \x00\n",
        "x: \x7f\n",
        "x: \uffff\n",
        DUPLICATE_SOURCE,
    ]:
        add_case(cases, "scalar-boundary-" + str(len(cases)), text)

    for text in ["TRUE: x\n012: x\n~: x\n.nan: x\n", "a: x\n", "value: +-1\n"]:
        add_case(cases, "authored-key-" + str(len(cases)), text)


def resolution_cases(cases: list[dict[str, Any]]) -> None:
    for text in ["İ: x\n", "ΟΣ: x\n", "İ: x\ni̇: y\n", "labels: {İ: {ΟΣ: x}}\n"]:
        for migration in ["accept", "reject"]:
            add_case(cases, "unicode-key-" + str(len(cases)), text, migration_policy=migration)

    for text in ["a:\nb: x\n", "-\n- x\n", "a: &a\nb: *a\n", "a: &a\n  text\nb: *a\n"]:
        add_case(cases, "implicit-value-" + str(len(cases)), text)

    for text in [
        "2026-1-2",
        "2026-01-02",
        "2026-1-2T1:00:00Z",
        "2026-1-2T123",
        "-.5",
        "+.5",
        "._",
    ]:
        add_case(cases, "emitter-resolution-" + str(len(cases)), json.dumps({"value": text}) + "\n")


def merge_cases(cases: list[dict[str, Any]]) -> None:
    add_case(
        cases,
        "merge-sequence-order",
        "first: &one {a: x}\nsecond: &two {b: y}\ntarget: {<<: [*one, *two], c: z}\n",
        migration_policy="accept",
    )

    add_case(
        cases,
        "merge-nested-sequence-order",
        "first: &one {a: x}\nsecond: &two {<<: *one, b: y}\nthird: &three {c: z}\ntarget: {<<: [*two, *three], d: q}\n",
        migration_policy="accept",
    )

    add_case(cases, "merge-nested-invalid", "target: {<<: {<<: 3}}\n", migration_policy="accept")

    add_case(cases, "undefined-alias-after-valid", "a: &ok x\nb: *ok\nc: *missing\n")

    add_case(cases, "simple-key-with-spaces", '"' + "word " * 20 + 'end": value\n', mapping_keys="data")


def render_cases(cases: list[dict[str, Any]]) -> None:
    for c in cases:
        if not c["error"]:
            c["rendered"] = yaml.safe_dump(
                _normalize_keys(
                    json.loads(json.dumps(c["value"])),
                    is_hashmap=c["options"].get("mapping_keys") == "literal",
                ),
                allow_unicode=False,
                default_flow_style=False,
                sort_keys=False,
            )


def source_ranges(cases: list[dict[str, Any]]) -> None:
    for c in cases:
        if c["error"]:
            continue
        ranges = {}
        keys = {}
        o = c["options"]
        load_sdl_yaml(
            c["source"],
            scope=MappingScope(o.get("mapping_keys", "structural")),
            base_pointer=o.get("base_pointer", ""),
            source_options=SDLSourceParseOptions(
                migration_policy=o.get("migration_policy", "reject"),
                limits=SDLParserLimits(**c["limits"]),
            ),
            source_locations=SDLSourceLocations(value_ranges=ranges, key_ranges=keys),
        )
        c["ranges"] = {k: v.as_dict() for k, v in ranges.items()}
        c["key_ranges"] = {k: v.as_dict() for k, v in keys.items()}


def record() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    scalar_cases(cases)
    profile_cases(cases)
    limit_cases(cases)
    edge_cases(cases)
    dialect_cases(cases)
    presentation_cases(cases)
    retained_cases(cases)
    boundary_cases(cases)
    resolution_cases(cases)
    merge_cases(cases)
    render_cases(cases)
    source_ranges(cases)
    commit = subprocess.check_output(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "implementations/python/packages/raes",
        ],
        cwd=ROOT,
        text=True,
    ).strip()

    return {"reference_commit": commit, "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without writing vectors")
    options = parser.parse_args()
    os.chdir(ROOT)
    document = record()
    encoded = json.dumps(document, indent=2, ensure_ascii=True) + "\n"
    if options.check:
        if OUTPUT.read_text() != encoded:
            print("source vectors differ from the reference", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(encoded)
    print(f"source vectors: {len(document['cases'])} cases match {document['reference_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
