"""Behavior authority scopes compile from the declaration that validation resolved (#1503)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from raes import build_declaration_index, instantiate_scenario, parse_sdl, parse_sdl_file
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler.alias_index import (
    _declared_runtime_addresses,
    _runtime_addressable_ref_index,
    _runtime_canonical_addresses,
)
from raes_processor.models import Diagnostic

REPO = Path(__file__).resolve().parents[3]
UNBOUND = "participant.behavior-specification-authority-scope-ref-unbound"
SPEC = "participant.behavior-specification.blue-behavior"
# What blue-behavior depends on before any authority scope adds to it.
BASE_DEPENDENCIES = (
    "participant.behavior.blue",
    "participant.action-contract.scan",
    "participant.observation-boundary.view",
)
_CONTRACT = {
    "semantic_version": "1.0.0",
    "behavioral_granularity": "atomic",
    "procedure_basis": "abstract transition",
    "realization_profile": "abstract",
    "fidelity_claim": "declared transition only",
    "preconditions": [{"precondition_id": "authorized", "precondition_class": "authority", "description": "grant"}],
    "effects": [{"effect_id": "none", "effect_class": "no_effect", "description": "compilation only"}],
    "failure_classes": ["authority_denied", "unknown"],
}
_BOUNDARY = {
    "projection_basis": "participant-local projection",
    "evidence_refs": ["evidence.scan-output"],
    "redaction_policy": "hidden refs never project",
    "latency_profile": "immediate",
}


def _behavior(authority_scope_refs: list[str]) -> dict:
    return {
        "semantic_version": "1.0.0",
        "lifecycle_state": "active",
        "participant_refs": ["blue"],
        "action_contract_refs": ["scan"],
        "observation_boundary_refs": ["view"],
        "authority_scope_refs": authority_scope_refs,
        "behavior_mode": "policy-directed",
    }


def _payload() -> dict:
    """Node `web` has services named after the node, an entity, an agent, a relationship and a content item."""

    services = ["web", "httpd", "ldap", "smtp", "playbook"]
    return deepcopy(
        {
            "name": "authority-scope-compilation",
            "nodes": {
                "net": {"type": "switch"},
                "web": {
                    "type": "compute",
                    "resources": {"ram": "1 GiB", "cpu": 1},
                    "services": [{"name": name, "port": 8000 + port} for port, name in enumerate(services)],
                },
            },
            "infrastructure": {
                "net": {"count": 1, "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}},
                "web": {"count": 1, "links": ["net"]},
            },
            "entities": {"org": {"role": "blue"}, "httpd": {"role": "blue"}},
            "relationships": {
                "link": {"type": "connects_to", "source": "web", "target": "nodes.web.services.web"},
                "smtp": {"type": "connects_to", "source": "web", "target": "nodes.web.services.smtp"},
            },
            "accounts": {"operator": {"username": "blue", "node": "web"}},
            "conditions": {"alive": {"command": "true", "interval": 5}},
            "features": {"hardening": {"type": "service"}},
            "content": {"docs": {"type": "dataset", "target": "web", "items": [{"name": "playbook"}]}},
            "action_contracts": {"scan": _CONTRACT},
            "observation_boundaries": {"view": _BOUNDARY},
            "agents": {"blue": {"actions": ["scan"], "observation_boundaries": ["view"]}, "ldap": {}},
            "behavior_specifications": {"blue-behavior": _behavior(["nodes.web"]), "watch": _behavior([])},
        }
    )


def _scenario_with_scope(ref: str):
    payload = _payload()
    payload["behavior_specifications"]["blue-behavior"]["authority_scope_refs"] = [ref]
    return parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize(
    ("ref", "declaration", "expected"),
    [
        # Each spelling below also names a node service in the compiler's alias map.
        ("web", "nodes.web", ("provision.node.web",)),
        ("httpd", "entities.httpd", ()),
        ("ldap", "agents.ldap", ()),
        ("smtp", "relationships.smtp", ()),
        ("playbook", "content.docs.items.playbook", ("provision.content.docs.items.playbook",)),
        # Runtime-addressable declarations named without a collision.
        ("nodes.web.services.web", "nodes.web.services.web", ("provision.node.web.service.web",)),
        ("net", "nodes.net", ("provision.network.net",)),
        ("infrastructure.net", "infrastructure.net", ("provision.network.net",)),
        ("operator", "accounts.operator", ("provision.account.operator",)),
        ("hardening", "features.hardening", ("template.feature.hardening",)),
        ("alive", "conditions.alive", ("template.condition.alive",)),
        ("scan", "action_contracts.scan", ("participant.action-contract.scan",)),
        ("view", "observation_boundaries.view", ("participant.observation-boundary.view",)),
        ("watch", "behavior_specifications.watch", ("participant.behavior-specification.watch",)),
        # Participant, organization and relationship scopes constrain only the semantic record.
        ("agents.blue", "agents.blue", ()),
        ("entities.org", "entities.org", ()),
        ("relationships.link", "relationships.link", ()),
    ],
)
def test_authority_scope_binds_the_declaration_validation_resolved(
    ref: str, declaration: str, expected: tuple[str, ...]
) -> None:
    scenario = _scenario_with_scope(ref)
    assert build_declaration_index(scenario).reference_aliases(targetable=True)[ref] == {declaration}

    model = compile_runtime_model(scenario)

    compiled = model.behavior_specifications[SPEC]
    assert compiled.authority_scope_refs == (ref,)
    assert compiled.authority_scope_addresses == expected
    assert compiled.refresh_dependencies == tuple(dict.fromkeys((*BASE_DEPENDENCIES, *expected)))
    assert [diagnostic for diagnostic in model.diagnostics if diagnostic.code == UNBOUND] == []


@pytest.mark.parametrize(
    "load",
    [
        lambda: parse_sdl(yaml.safe_dump(_payload())),
        lambda: parse_sdl_file(REPO / "examples/scenarios/enterprise-participant-evidence-loop.sdl.yaml"),
        lambda: parse_sdl_file(
            REPO / "implementations/python/tests/fixtures/behavior-authoring/twice-imported.sdl.yaml"
        ),
    ],
    ids=["collisions", "enterprise-example", "twice-imported-module"],
)
def test_canonical_runtime_addresses_are_declared_addresses(load) -> None:
    """Differential check: the compiler's canonical keys are the declaration index's own addresses."""

    scenario = instantiate_scenario(load())
    canonical = _runtime_canonical_addresses(scenario)
    aliases = _runtime_addressable_ref_index(scenario)

    assert canonical
    assert set(canonical) <= build_declaration_index(scenario).addresses
    assert all(aliases[declaration] == {address} for declaration, address in canonical.items())


@pytest.mark.parametrize("candidates", [set(), {"nodes.web", "conditions.web"}], ids=["no-candidate", "two"])
def test_unresolvable_authority_scope_is_reported_not_dropped(candidates: set[str]) -> None:
    diagnostics: list[Diagnostic] = []

    addresses = _declared_runtime_addresses(
        ["web"],
        resolve=lambda _ref: set(candidates),
        canonical_addresses={"nodes.web": "provision.node.web"},
        owner_address=SPEC,
        diagnostic_code=UNBOUND,
        diagnostics=diagnostics,
    )

    assert addresses == ()
    (diagnostic,) = diagnostics
    assert (diagnostic.code, diagnostic.domain, diagnostic.address, diagnostic.is_error) == (
        UNBOUND,
        "participant",
        SPEC,
        True,
    )
    assert f"'web' resolves to {len(candidates)} declarations" in diagnostic.message
