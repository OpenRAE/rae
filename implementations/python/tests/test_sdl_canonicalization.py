"""Canonical semantic identity tests for ``raes-sdl-semantic/v2``."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from raes import (
    SDL_CANONICAL_PROFILE,
    SDLMigrationPolicy,
    SDLParseError,
    canonical_sdl_bytes,
    canonical_sdl_digest,
    format_sdl_source,
    instantiate_scenario,
    parse_sdl,
    parse_sdl_file,
)


def test_semantically_identical_source_spellings_have_identical_canonical_bytes() -> None:
    canonical = parse_sdl(
        textwrap.dedent(
            """
            name: equivalent
            description: same
            nodes:
              web: {type: switch}
            """
        )
    )
    migrated = parse_sdl(
        textwrap.dedent(
            """
            Description: same
            Name: equivalent
            nodes:
              web: {Type: SWITCH}
            """
        ),
        migration_policy=SDLMigrationPolicy.ACCEPT,
    )

    assert canonical_sdl_bytes(canonical) == canonical_sdl_bytes(migrated)


def test_format_round_trip_preserves_semantic_identity_and_canonical_bytes() -> None:
    source = textwrap.dedent(
        """
        Description: same
        Name: round-trip
        nodes:
          web-app: {Type: SWITCH}
        """
    )
    before = parse_sdl(source, migration_policy=SDLMigrationPolicy.ACCEPT)

    formatted = format_sdl_source(source).content
    after = parse_sdl(formatted)

    assert canonical_sdl_bytes(after) == canonical_sdl_bytes(before)
    assert format_sdl_source(formatted).content == formatted


def test_canonical_digest_is_profile_labelled_and_repeatable() -> None:
    scenario = parse_sdl("name: digest-example\n")

    first = canonical_sdl_digest(scenario)
    second = canonical_sdl_digest(scenario)

    assert first == second
    assert first.profile == SDL_CANONICAL_PROFILE == "raes-sdl-semantic/v2"
    assert first.algorithm == "sha256"
    assert first.value.startswith("sha256:")
    assert len(first.value) == len("sha256:") + 64
    assert first.as_dict() == {
        "profile": "raes-sdl-semantic/v2",
        "algorithm": "sha256",
        "value": first.value,
    }


def test_canonical_bytes_preserve_authored_field_presence() -> None:
    omitted = parse_sdl("name: presence\n")
    explicit = parse_sdl("name: presence\ndescription: ''\n")

    assert canonical_sdl_bytes(omitted) != canonical_sdl_bytes(explicit)


def test_canonical_bytes_do_not_normalize_unicode() -> None:
    composed = parse_sdl("name: unicode\ndescription: caf\N{LATIN SMALL LETTER E WITH ACUTE}\n")
    decomposed = parse_sdl("name: unicode\ndescription: cafe\N{COMBINING ACUTE ACCENT}\n")

    assert canonical_sdl_bytes(composed) != canonical_sdl_bytes(decomposed)


def test_canonical_bytes_are_map_order_independent_and_array_order_sensitive() -> None:
    first = parse_sdl(
        textwrap.dedent(
            """
            name: ordering
            module:
              id: raes/ordering
              version: 1.0.0
              parameters: [alpha, beta]
            """
        )
    )
    reordered_map = parse_sdl(
        textwrap.dedent(
            """
            module:
              parameters: [alpha, beta]
              version: 1.0.0
              id: raes/ordering
            name: ordering
            """
        )
    )
    reordered_array = parse_sdl(
        textwrap.dedent(
            """
            name: ordering
            module:
              id: raes/ordering
              version: 1.0.0
              parameters: [beta, alpha]
            """
        )
    )

    assert canonical_sdl_bytes(first) == canonical_sdl_bytes(reordered_map)
    assert canonical_sdl_bytes(first) != canonical_sdl_bytes(reordered_array)


def test_canonical_identity_requires_validated_authoring_scenario() -> None:
    unvalidated = parse_sdl("name: unvalidated\n", skip_semantic_validation=True)
    with pytest.raises(SDLParseError, match="semantic validation"):
        canonical_sdl_bytes(unvalidated)

    validated = parse_sdl("name: instantiated\n")
    instantiated = instantiate_scenario(validated)
    with pytest.raises(SDLParseError, match="authoring scenario"):
        canonical_sdl_bytes(instantiated)


def test_canonical_payload_carries_profile_and_module_provenance_channels() -> None:
    payload = canonical_sdl_bytes(parse_sdl("name: envelope\n"))

    assert payload.startswith(b'{"module_node_variable_refs":{}')
    assert b'"module_variable_specs":{}' in payload
    assert b'"profile":"raes-sdl-semantic/v2"' in payload
    assert b'"scenario":{"name":"envelope"}' in payload


def test_canonical_identity_rejects_values_outside_the_jcs_integer_domain() -> None:
    scenario = parse_sdl(
        """\
name: unsafe-integer
variables:
  too_large:
    type: integer
    default: 9007199254740992
"""
    )

    with pytest.raises(SDLParseError, match="canonicalization failed"):
        canonical_sdl_bytes(scenario)


def test_canonical_payload_commits_to_imported_variable_provenance(tmp_path: Path) -> None:
    module = tmp_path / "module.yaml"
    module.write_text(
        """\
name: module
module:
  id: acme/module
  version: 1.0.0
  parameters: [image_os]
  exports:
    nodes: [host]
    infrastructure: [host]
variables:
  image_os:
    type: string
    default: linux
    allowed_values: [linux]
nodes:
  host:
    type: compute
    os: ${image_os}
    resources: {ram: 1 gib, cpu: 1}
infrastructure:
  host: {count: 1}
""",
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """\
name: root
imports:
  - path: module.yaml
    namespace: imported
""",
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    payload = canonical_sdl_bytes(scenario)

    variable_name = "imported.__private.image_os"
    assert scenario.module_variable_specs[variable_name]["allowed_values"] == ["linux"]
    assert scenario.module_node_variable_refs["imported.host"]["os"] == variable_name
    assert b'"module_variable_specs":{"imported.__private.image_os"' in payload
    assert b'"module_node_variable_refs":{"imported.host"' in payload
