"""DSL-117 participant-local interactive-access authoring and carriage."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from raes import (
    SDLInstantiationError,
    SDLParseError,
    SDLValidationError,
    instantiate_scenario,
    parse_sdl,
    parse_sdl_file,
)
from raes.language_service import language_completions, language_references
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model

REPO_ROOT = Path(__file__).resolve().parents[3]


def _scenario(*, access: str = "") -> str:
    source = textwrap.dedent(
        """
        name: participant-interactive-access
        nodes:
          workstation:
            type: compute
            os: windows
            resources: {ram: 2 GiB, cpu: 2}
            services:
              - {name: ssh, port: 22}
          other-host:
            type: compute
            os: linux
            resources: {ram: 1 GiB, cpu: 1}
          transit:
            type: switch
        accounts:
          operator:
            username: operator
            node: workstation
          other-user:
            username: other
            node: other-host
        entities:
          blue-team:
            role: blue
        agents:
          blue-participant:
            affiliations: [blue-team]
            starting_accounts: [operator]
        """
    )
    if not access:
        return source
    marker = "    starting_accounts: [operator]\n"
    access_block = textwrap.indent(textwrap.dedent(access).strip(), "    ")
    return source.replace(marker, f"{marker}{access_block}\n", 1)


def _two_access_bindings() -> str:
    return """
    interactive_access:
      primary-shell:
        target_ref: workstation
        channel: ssh
        account_ref: operator
      desktop-console:
        target_ref: nodes.workstation
        channel: rdp
        account_ref: accounts.operator
    """


def _collect_enum_sets(value: object) -> set[frozenset[str]]:
    if isinstance(value, dict):
        found = {frozenset(value["enum"])} if isinstance(value.get("enum"), list) else set()
        for child in value.values():
            found.update(_collect_enum_sets(child))
        return found
    if isinstance(value, list):
        found: set[frozenset[str]] = set()
        for child in value:
            found.update(_collect_enum_sets(child))
        return found
    return set()


def test_participant_interactive_access_is_keyed_typed_and_role_neutral() -> None:
    scenario = parse_sdl(_scenario(access=_two_access_bindings()))

    participant = scenario.agents["blue-participant"]
    assert tuple(participant.interactive_access) == ("primary-shell", "desktop-console")
    assert participant.interactive_access["primary-shell"].target_ref == "workstation"
    assert participant.interactive_access["primary-shell"].channel.value == "ssh"
    assert participant.interactive_access["desktop-console"].channel.value == "rdp"
    assert participant.interactive_access["desktop-console"].account_ref == "accounts.operator"


def test_absence_is_empty_and_never_inferred_from_os_service_or_account() -> None:
    scenario = parse_sdl(_scenario())

    assert scenario.agents["blue-participant"].interactive_access == {}


@pytest.mark.parametrize("channel", ["telnet", "vnc", "https", "SSH://host"])
def test_interactive_access_channel_is_closed(channel: str) -> None:
    access = f"""
    interactive_access:
      console:
        target_ref: workstation
        channel: {channel}
        account_ref: operator
    """
    source = _scenario(access=access)

    with pytest.raises(SDLParseError, match="channel must be one of: ssh, rdp"):
        parse_sdl(source)


@pytest.mark.parametrize("field", ["host", "port", "url", "credential", "password", "secret_ref"])
def test_interactive_access_rejects_locator_and_secret_fields(field: str) -> None:
    access = f"""
    interactive_access:
      console:
        target_ref: workstation
        channel: ssh
        account_ref: operator
        {field}: forbidden
    """
    source = _scenario(access=access)

    with pytest.raises(SDLParseError, match="Extra inputs are not permitted"):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("access", "message"),
    [
        (
            """
            interactive_access:
              console: {target_ref: ghost, channel: ssh, account_ref: operator}
            """,
            "target_ref 'ghost' does not reference a declared compute node",
        ),
        (
            """
            interactive_access:
              console: {target_ref: transit, channel: ssh, account_ref: operator}
            """,
            "target_ref 'transit' must reference a compute node",
        ),
        (
            """
            interactive_access:
              console: {target_ref: workstation, channel: ssh, account_ref: ghost}
            """,
            "account_ref 'ghost' does not reference a declared account",
        ),
        (
            """
            interactive_access:
              console: {target_ref: workstation, channel: ssh, account_ref: other-user}
            """,
            "account_ref 'other-user' belongs to node 'other-host', not target 'workstation'",
        ),
        (
            """
            interactive_access:
              console: {target_ref: workstation, channel: ssh}
              unauthorized: {target_ref: other-host, channel: rdp, account_ref: other-user}
            """,
            "account_ref 'other-user' is not in starting_accounts",
        ),
    ],
)
def test_interactive_access_reference_and_authority_invariants(access: str, message: str) -> None:
    source = _scenario(access=access)

    with pytest.raises(SDLValidationError, match=message):
        parse_sdl(source)


def test_duplicate_canonical_target_channel_is_rejected_per_participant() -> None:
    access = """
    interactive_access:
      first: {target_ref: workstation, channel: ssh, account_ref: operator}
      second: {target_ref: nodes.workstation, channel: ssh, account_ref: accounts.operator}
    """
    source = _scenario(access=access)

    with pytest.raises(SDLValidationError, match="duplicates interactive_access target/channel.*workstation.*ssh"):
        parse_sdl(source)


def test_same_target_channel_is_valid_for_different_participants() -> None:
    peer = textwrap.indent(
        textwrap.dedent(
            """
            peer-participant:
              affiliations: [blue-team]
              starting_accounts: [operator]
              interactive_access:
                peer-shell: {target_ref: workstation, channel: ssh, account_ref: operator}
            """
        ).strip(),
        "  ",
    )
    source = _scenario(access=_two_access_bindings()).replace(
        "  blue-participant:\n",
        f"{peer}\n  blue-participant:\n",
        1,
    )

    scenario = parse_sdl(source)

    assert scenario.agents["blue-participant"].interactive_access
    assert scenario.agents["peer-participant"].interactive_access["peer-shell"].channel.value == "ssh"


def test_whole_field_variables_are_revalidated_after_instantiation() -> None:
    source = _scenario(
        access="""
        interactive_access:
          console:
            target_ref: ${target}
            channel: ${channel}
            account_ref: ${account}
        """
    ).replace(
        "nodes:\n",
        textwrap.dedent(
            """
            variables:
              target: {type: string, default: workstation, allowed_values: [workstation, ghost]}
              channel: {type: string, default: ssh, allowed_values: [ssh, rdp, telnet]}
              account: {type: string, default: operator, allowed_values: [operator, other-user]}
            nodes:
            """
        ),
        1,
    )
    authored = parse_sdl(source)

    concrete = instantiate_scenario(
        authored,
        parameters={"target": "workstation", "channel": "rdp", "account": "operator"},
    )
    assert concrete.agents["blue-participant"].interactive_access["console"].channel.value == "rdp"

    with pytest.raises(
        SDLInstantiationError,
        match="/agents/blue-participant/interactive_access/console/channel",
    ):
        instantiate_scenario(
            authored,
            parameters={"target": "workstation", "channel": "telnet", "account": "operator"},
        )

    with pytest.raises(SDLInstantiationError, match="belongs to node 'other-host'"):
        instantiate_scenario(
            authored,
            parameters={"target": "workstation", "channel": "ssh", "account": "other-user"},
        )


def test_module_composition_rewrites_bare_and_qualified_access_refs(tmp_path: Path) -> None:
    module = tmp_path / "participant.yaml"
    module.write_text(
        textwrap.dedent(
            """
            name: participant-module
            module:
              id: acme/participant
              version: 1.0.0
              exports:
                nodes: [vm]
                accounts: [login]
                entities: [team]
                agents: [operator]
            nodes:
              vm: {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}}
            accounts:
              login: {username: operator, node: vm}
            entities:
              team: {role: blue}
            agents:
              operator:
                affiliations: [team]
                starting_accounts: [login]
                interactive_access:
                  shell: {target_ref: vm, channel: ssh, account_ref: login}
                  desktop: {target_ref: nodes.vm, channel: rdp, account_ref: accounts.login}
            """
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: composed
            imports:
              - path: participant.yaml
                namespace: shared
            """
        ),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    access = scenario.agents["shared.operator"].interactive_access

    assert access["shell"].target_ref == "shared.vm"
    assert access["shell"].account_ref == "shared.login"
    assert access["desktop"].target_ref == "nodes.shared.vm"
    assert access["desktop"].account_ref == "accounts.shared.login"


def test_language_service_exposes_access_fields_and_typed_references() -> None:
    source = _scenario(access=_two_access_bindings())

    participant_fields = language_completions(source, cursor_path="/agents/blue-participant")
    targets = language_completions(
        source,
        cursor_path="/agents/blue-participant/interactive_access/primary-shell/target_ref",
    )
    accounts = language_completions(
        source,
        cursor_path="/agents/blue-participant/interactive_access/primary-shell/account_ref",
    )
    references = language_references(source, "nodes.workstation")

    assert "interactive_access" in {item["label"] for item in participant_fields["items"]}
    assert "nodes.workstation" in {item["detail"] for item in targets["items"]}
    assert "accounts.operator" in {item["detail"] for item in accounts["items"]}
    assert any(item["path"].endswith("/target_ref") for item in references["occurrences"])


def test_compiler_carries_typed_access_and_refresh_dependencies() -> None:
    model = compile_runtime_model(parse_sdl(_scenario(access=_two_access_bindings())))
    participant = model.participant_behaviors["participant.behavior.blue-participant"]

    assert [(item.access_id, item.channel) for item in participant.interactive_access] == [
        ("desktop-console", "rdp"),
        ("primary-shell", "ssh"),
    ]
    primary = participant.interactive_access[1]
    assert primary.target_ref == "workstation"
    assert primary.target_address == "provision.node.workstation"
    assert primary.account_ref == "operator"
    assert primary.account_address == "provision.account.operator"
    assert "provision.node.workstation" in participant.refresh_dependencies
    assert "provision.account.operator" in participant.refresh_dependencies


def test_authoring_and_instantiated_schemas_publish_closed_access_shape() -> None:
    schemas = schema_bundle()
    authoring = schemas["sdl-authoring-input-v1"]
    instantiated = schemas["instantiated-scenario-v1"]
    snapshot = schemas["instantiated-scenario-snapshot-v1"]

    assert "interactive_access" in authoring["$defs"]["Agent"]["properties"]
    assert authoring["$defs"]["ParticipantInteractiveAccess"]["additionalProperties"] is False
    for schema in (authoring, instantiated, snapshot):
        access_registry = schema["$defs"]["Agent"]["properties"]["interactive_access"]
        assert access_registry["additionalProperties"] is False
    assert frozenset({"ssh", "rdp"}) in _collect_enum_sets(authoring)
    assert frozenset({"ssh", "rdp"}) in _collect_enum_sets(instantiated)
    assert "x-raes-variable-reference" in json.dumps(authoring)
    assert "x-raes-variable-reference" not in json.dumps(instantiated)


def test_channel_enum_matches_controlled_vocabulary_authority() -> None:
    catalog = json.loads(
        (REPO_ROOT / "contracts" / "concept-authority" / "controlled-vocabularies-v1.json").read_text(encoding="utf-8")
    )

    vocabulary = catalog["vocabularies"]["participant-interactive-access-channels"]
    assert vocabulary["kind"] == "enumeration"
    assert vocabulary["extension_policy"] == "closed"
    assert vocabulary["governed_scopes"] == ["agents.interactive_access.channel"]
    assert set(vocabulary["terms"]) == {"ssh", "rdp"}
