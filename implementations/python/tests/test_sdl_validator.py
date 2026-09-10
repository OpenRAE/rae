"""Tests for SDL semantic validation."""

import pytest
from pydantic import ValidationError
from raes._errors import SDLValidationError
from raes.scenario import Scenario
from raes.validator import SemanticValidator


def _validate(scenario: Scenario) -> list[str]:
    """Run validation and return errors (empty list = valid)."""
    v = SemanticValidator(scenario)
    try:
        v.validate()
        return []
    except SDLValidationError as e:
        return e.errors


def _make_scenario(**kwargs) -> Scenario:
    """Build a minimal valid scenario with overrides."""
    defaults = {"name": "test-scenario"}
    defaults.update(kwargs)
    return Scenario(**defaults)


# ---------------------------------------------------------------------------
# OCR cross-reference validation
# ---------------------------------------------------------------------------


class TestVerifyNodes:
    def test_undefined_feature_reference(self):
        s = _make_scenario(
            nodes={
                "vm-1": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "features": {"nonexistent": "admin"},
                    "roles": {"admin": {"username": "user"}},
                }
            },
        )
        errors = _validate(s)
        assert any("undefined feature" in e for e in errors)

    def test_undefined_vulnerability_on_node(self):
        with pytest.raises(ValidationError, match="classification migration"):
            _make_scenario(nodes={"web": {"type": "compute", "vulnerabilities": ["unknown"]}})

    def test_node_name_too_long(self):
        long_name = "a" * 36
        with pytest.raises(ValidationError, match="35 characters"):
            _make_scenario(nodes={long_name: {"type": "switch"}})

    @pytest.mark.parametrize(
        ("field_name", "section_name", "section_value", "error_fragment"),
        [
            ("features", "features", {"svc": {"type": "service"}}, "feature 'svc' references undefined role"),
            (
                "conditions",
                "conditions",
                {"check": {"command": "/bin/check", "interval": 10}},
                "condition 'check' references undefined role",
            ),
            ("injects", "injects", {"email": {}}, "inject 'email' references undefined role"),
        ],
    )
    def test_role_binding_requires_declared_role(
        self,
        field_name,
        section_name,
        section_value,
        error_fragment,
    ):
        s = _make_scenario(
            nodes={
                "vm-1": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    field_name: {next(iter(section_value.keys())): "admin"},
                }
            },
            **{section_name: section_value},
        )
        errors = _validate(s)
        assert any(error_fragment in e for e in errors)


class TestVerifyInfrastructure:
    def test_infra_without_matching_node(self):
        s = _make_scenario(
            infrastructure={"ghost": {"count": 1}},
        )
        errors = _validate(s)
        assert any("does not match" in e for e in errors)

    def test_link_to_undefined_infra(self):
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}, "vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            infrastructure={
                "sw": {"count": 1},
                "vm": {"count": 1, "links": ["nonexistent"]},
            },
        )
        errors = _validate(s)
        assert any("undefined" in e for e in errors)

    def test_switch_count_exceeds_one(self):
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            infrastructure={"sw": {"count": 2}},
        )
        errors = _validate(s)
        assert any("count > 1" in e for e in errors)

    def test_links_must_reference_switch_entries(self):
        s = _make_scenario(
            nodes={
                "vm-a": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
                "vm-b": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            infrastructure={
                "vm-a": {"count": 1, "links": ["vm-b"]},
                "vm-b": {"count": 1},
            },
        )
        errors = _validate(s)
        assert any("must reference a switch/network entry" in e for e in errors)

    def test_invalid_per_link_ip_is_rejected(self):
        s = _make_scenario(
            nodes={
                "sw": {"type": "switch"},
                "vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            infrastructure={
                "sw": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                },
                "vm": {
                    "count": 1,
                    "links": ["sw"],
                    "properties": [{"sw": "not-an-ip"}],
                },
            },
        )
        errors = _validate(s)
        assert any("invalid IP assignment" in e for e in errors)

    def test_conditioned_node_cannot_scale_above_one(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "conditions": {"check": "admin"},
                    "roles": {"admin": {"username": "ops"}},
                }
            },
            infrastructure={"vm": {"count": 3}},
            conditions={"check": {"command": "/bin/check", "interval": 10}},
        )
        errors = _validate(s)
        assert any("cannot have count > 1" in e for e in errors)


class TestVerifyRuntimeNetwork:
    def test_endpoint_referencing_switch_is_valid(self):
        s = _make_scenario(
            nodes={
                "sw": {"type": "switch"},
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {
                        "network": {"endpoints": [{"network": "sw", "ip_address": "10.0.0.5", "gateway": "10.0.0.1"}]}
                    },
                },
            },
            infrastructure={
                "sw": {"count": 1, "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}},
                "vm": {"count": 1, "links": ["sw"]},
            },
        )
        assert _validate(s) == []

    def test_endpoint_referencing_undefined_network_is_rejected(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {"network": {"endpoints": [{"network": "ghost-net"}]}},
                },
            },
        )
        errors = _validate(s)
        assert any("references undefined network 'ghost-net'" in e for e in errors)

    def test_endpoint_referencing_non_switch_is_rejected(self):
        s = _make_scenario(
            nodes={
                "other-vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {"network": {"endpoints": [{"network": "other-vm"}]}},
                },
            },
            infrastructure={
                "other-vm": {"count": 1},
                "vm": {"count": 1},
            },
        )
        errors = _validate(s)
        assert any("must reference a switch/network entry" in e for e in errors)

    def test_endpoint_ip_outside_referenced_cidr_is_rejected(self):
        s = _make_scenario(
            nodes={
                "sw": {"type": "switch"},
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {"network": {"endpoints": [{"network": "sw", "ip_address": "192.168.5.5"}]}},
                },
            },
            infrastructure={
                "sw": {"count": 1, "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}},
                "vm": {"count": 1, "links": ["sw"]},
            },
        )
        errors = _validate(s)
        assert any("ip_address 192.168.5.5 is not within network 'sw'" in e for e in errors)

    def test_endpoint_network_variable_reference_is_skipped(self):
        s = _make_scenario(
            variables={"target_net": {"type": "string", "required": True}},
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {"network": {"endpoints": [{"network": "${target_net}"}]}},
                },
            },
        )
        assert _validate(s) == []


class TestVerifyRuntimeCapabilityOverrides:
    def test_override_subject_matching_observed_process_is_valid(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {
                        "processes": [
                            {"name": "entrypoint", "pid": 1, "role": "supervisor"},
                            {"name": "sshd", "parent_pid": 1, "role": "supervisor"},
                        ],
                        "linux_capabilities": {
                            "required": ["CAP_AUDIT_CONTROL"],
                            "process_overrides": [
                                {
                                    "subject": {"name": "sshd"},
                                    "scope": "subtree",
                                    "drop": ["CAP_AUDIT_CONTROL"],
                                }
                            ],
                        },
                    },
                },
            },
        )
        assert _validate(s) == []

    def test_override_subject_missing_from_processes_is_rejected(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {
                        "processes": [
                            {"name": "entrypoint", "pid": 1, "role": "supervisor"},
                        ],
                        "linux_capabilities": {
                            "process_overrides": [
                                {
                                    "subject": {"name": "ghost-sshd"},
                                    "scope": "subtree",
                                    "drop": ["CAP_AUDIT_CONTROL"],
                                }
                            ],
                        },
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("capability override subject 'ghost-sshd' does not match any process" in e for e in errors)

    def test_override_with_variable_subject_name_is_skipped(self):
        s = _make_scenario(
            variables={"shell_name": {"type": "string", "required": True}},
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {
                        "processes": [
                            {"name": "entrypoint", "pid": 1, "role": "supervisor"},
                        ],
                        "linux_capabilities": {
                            "process_overrides": [
                                {
                                    "subject": {"name": "${shell_name}"},
                                    "scope": "subtree",
                                    "drop": ["CAP_AUDIT_CONTROL"],
                                }
                            ],
                        },
                    },
                },
            },
        )
        assert _validate(s) == []

    def test_override_skipped_when_no_processes_declared(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "runtime": {
                        "linux_capabilities": {
                            "process_overrides": [
                                {
                                    "subject": {"name": "sshd", "parent_pid": 1},
                                    "scope": "subtree",
                                    "drop": ["CAP_AUDIT_CONTROL"],
                                }
                            ],
                        },
                    },
                },
            },
        )
        assert _validate(s) == []


class TestVerifyFeatures:
    def test_feature_dependency_cycle(self):
        s = _make_scenario(
            features={
                "a": {"type": "service", "dependencies": ["b"]},
                "b": {"type": "service", "dependencies": ["a"]},
            },
        )
        errors = _validate(s)
        assert any("cycle" in e for e in errors)

    def test_feature_references_undefined_vuln(self):
        with pytest.raises(ValidationError, match="classification migration"):
            _make_scenario(features={"service": {"type": "service", "vulnerabilities": ["unknown"]}})

    def test_valid_feature_dependencies(self):
        s = _make_scenario(
            features={
                "a": {"type": "service"},
                "b": {"type": "configuration", "dependencies": ["a"]},
            },
        )
        errors = _validate(s)
        assert not errors


class TestVerifyInjects:
    def test_inject_references_undefined_entity(self):
        s = _make_scenario(
            entities={"red": {"role": "red"}},
            injects={
                "inj": {"from_entity": "red", "to_entities": ["missing"]},
            },
        )
        errors = _validate(s)
        assert any("not a defined entity" in e for e in errors)


class TestVerifyEvents:
    def test_event_references_undefined_assertion(self):
        s = _make_scenario(
            events={"e1": {"assertions": ["missing"]}},
        )
        errors = _validate(s)
        assert any("assertion 'missing' not in assertions section" in e for e in errors)


class TestVerifyScripts:
    def test_script_references_undefined_event(self):
        s = _make_scenario(
            scripts={
                "s1": {
                    "start_time": 0,
                    "end_time": 3600,
                    "speed": 1.0,
                    "events": {"missing": 600},
                }
            },
        )
        errors = _validate(s)
        assert any("undefined event" in e for e in errors)


class TestVerifyStories:
    def test_story_references_undefined_script(self):
        s = _make_scenario(
            stories={"st1": {"scripts": ["missing"]}},
        )
        errors = _validate(s)
        assert any("undefined script" in e for e in errors)


# ---------------------------------------------------------------------------
# RAES extension validation
# ---------------------------------------------------------------------------


class TestErrorCollection:
    def test_multiple_errors_collected(self):
        """Validator collects all errors, not just the first."""
        s = _make_scenario(
            features={
                "f1": {"type": "service", "dependencies": ["missing-1"]},
                "f2": {"type": "service", "dependencies": ["missing-2"]},
                "f3": {"type": "service", "dependencies": ["missing-3"]},
            },
        )
        errors = _validate(s)
        assert len(errors) >= 3


class TestVerifyContent:
    def test_content_targets_undefined_node(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            content={"data": {"type": "file", "target": "ghost-node", "path": "/tmp/x"}},
        )
        errors = _validate(s)
        assert any("undefined node" in e for e in errors)

    def test_valid_content_passes(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            content={"data": {"type": "file", "target": "vm", "path": "/tmp/flag"}},
        )
        errors = _validate(s)
        assert not errors

    def test_content_target_must_be_vm(self):
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            content={"data": {"type": "file", "target": "sw", "path": "/tmp/flag"}},
        )
        errors = _validate(s)
        assert any("must be a compute node" in e for e in errors)


class TestVerifyAccounts:
    def test_account_references_undefined_node(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            accounts={"user": {"username": "admin", "node": "ghost-node"}},
        )
        errors = _validate(s)
        assert any("undefined node" in e for e in errors)

    def test_valid_account_passes(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            accounts={"user": {"username": "admin", "node": "vm"}},
        )
        errors = _validate(s)
        assert not errors

    def test_account_node_must_be_vm(self):
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            accounts={"user": {"username": "admin", "node": "sw"}},
        )
        errors = _validate(s)
        assert any("must be a compute node" in e for e in errors)


class TestVerifyACLs:
    def test_acl_references_undefined_network(self):
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            infrastructure={
                "sw": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                    "acls": [{"direction": "in", "from_net": "ghost-net", "action": "deny"}],
                },
            },
        )
        errors = _validate(s)
        assert any("undefined network" in e for e in errors)

    def test_acl_to_net_checked_when_from_net_valid(self):
        # When ``from_net`` is a valid declared switch but ``to_net`` is
        # bogus, validation must (a) surface the bad ``to_net`` reference
        # AND (b) not raise a spurious error for the valid ``from_net``.
        # The complementary `test_acl_references_undefined_network` case
        # covers the inverse (bogus ``from_net``, no ``to_net``).
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            infrastructure={
                "sw": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                    "acls": [
                        {
                            "direction": "in",
                            "from_net": "sw",
                            "to_net": "ghost-net",
                            "action": "deny",
                        }
                    ],
                },
            },
        )
        errors = _validate(s)
        assert any("ghost-net" in e for e in errors), errors
        # The valid `from_net: "sw"` must not be flagged as a bad reference.
        # The owner-label substring `Infrastructure 'sw'` legitimately
        # appears in the `to_net` error and is excluded explicitly.
        assert not any("'sw'" in e.replace("Infrastructure 'sw'", "") and "undefined" in e for e in errors), errors

    def test_acl_both_endpoints_reported_when_both_bogus(self):
        # When BOTH ``from_net`` and ``to_net`` are unknown, validation
        # reports both names so the author can fix them in one pass.
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            infrastructure={
                "sw": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                    "acls": [
                        {
                            "direction": "in",
                            "from_net": "ghost-from",
                            "to_net": "ghost-to",
                            "action": "deny",
                        }
                    ],
                },
            },
        )
        errors = _validate(s)
        assert any("ghost-from" in e for e in errors), errors
        assert any("ghost-to" in e for e in errors), errors


class TestFeatureListShorthand:
    def test_features_as_list_with_empty_role(self):
        """Nodes with features as list (no role) should validate."""
        from raes import parse_sdl

        s = parse_sdl("""
name: shorthand-test
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    features: [svc-a, svc-b]
features:
  svc-a: {type: Service, source: pkg-a}
  svc-b: {type: Service, source: pkg-b}
""")
        assert "svc-a" in s.nodes["vm"].features
        assert s.nodes["vm"].features["svc-a"] == ""


class TestVerifyRelationships:
    def test_undefined_source(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            features={"svc": {"type": "service"}},
            relationships={"r1": {"type": "connects_to", "source": "ghost", "target": "svc"}},
        )
        errors = _validate(s)
        assert any("does not reference" in e for e in errors)

    def test_undefined_target(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            features={"svc": {"type": "service"}},
            relationships={"r1": {"type": "connects_to", "source": "svc", "target": "ghost"}},
        )
        errors = _validate(s)
        assert any("does not reference" in e for e in errors)

    def test_valid_relationship(self):
        s = _make_scenario(
            features={
                "exchange": {"type": "service"},
                "ad-ds": {"type": "service"},
            },
            relationships={
                "auth": {"type": "authenticates_with", "source": "exchange", "target": "ad-ds"},
            },
        )
        errors = _validate(s)
        assert not errors

    def test_relationship_rejects_non_targetable_variable(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            variables={"env": {"type": "string", "default": "prod"}},
            relationships={"r1": {"type": "connects_to", "source": "vm", "target": "env"}},
        )
        errors = _validate(s)
        assert any("does not reference any defined targetable element" in error for error in errors)

    def test_relationship_can_target_other_relationship(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            relationships={
                "r1": {"type": "connects_to", "source": "vm", "target": "vm"},
                "r2": {"type": "depends_on", "source": "vm", "target": "r1"},
            },
        )
        errors = _validate(s)
        assert not errors

    def test_relationship_can_target_content_item_name(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            content={
                "dataset": {
                    "type": "dataset",
                    "target": "vm",
                    "items": [{"name": "budget-email", "display_name": "budget.eml"}],
                }
            },
            relationships={
                "r1": {"type": "connects_to", "source": "vm", "target": "budget-email"},
            },
        )
        errors = _validate(s)
        assert not errors

    def test_relationship_rejects_ambiguous_bare_ref(self):
        s = _make_scenario(
            nodes={"web": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            features={"web": {"type": "service", "source": {"name": "nginx"}}},
            relationships={"r1": {"type": "connects_to", "source": "web", "target": "web"}},
        )
        errors = _validate(s)
        assert any("source 'web' is ambiguous" in e for e in errors)
        assert any("nodes.web" in e and "features.web" in e for e in errors)

    def test_relationship_accepts_section_qualified_refs(self):
        s = _make_scenario(
            nodes={"web": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            features={"web": {"type": "service", "source": {"name": "nginx"}}},
            relationships={
                "r1": {
                    "type": "depends_on",
                    "source": "features.web",
                    "target": "nodes.web",
                }
            },
        )
        errors = _validate(s)
        assert not errors

    def test_relationship_accepts_qualified_content_item_ref(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            content={
                "dataset-a": {
                    "type": "dataset",
                    "target": "vm",
                    "items": [{"name": "shared"}],
                },
                "dataset-b": {
                    "type": "dataset",
                    "target": "vm",
                    "items": [{"name": "shared"}],
                },
            },
            relationships={
                "r1": {
                    "type": "connects_to",
                    "source": "content.dataset-a.items.shared",
                    "target": "nodes.vm",
                },
            },
        )
        errors = _validate(s)
        assert not errors


class TestVerifyAgents:
    def test_undefined_entity(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            agents={"a1": {"entity": "ghost-team", "actions": ["scan"]}},
        )
        errors = _validate(s)
        assert any("undefined entity" in e for e in errors)

    def test_undefined_starting_account(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            entities={"red": {"role": "red"}},
            agents={"a1": {"entity": "red", "starting_accounts": ["ghost-acct"]}},
        )
        errors = _validate(s)
        assert any("not in accounts" in e for e in errors)

    def test_undefined_allowed_subnet(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            entities={"red": {"role": "red"}},
            agents={"a1": {"entity": "red", "allowed_subnets": ["ghost-net"]}},
        )
        errors = _validate(s)
        assert any("not in infrastructure" in e for e in errors)

    def test_undefined_initial_knowledge_host(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            entities={"red": {"role": "red"}},
            agents={
                "a1": {
                    "entity": "red",
                    "initial_knowledge": {"hosts": ["ghost-host"]},
                }
            },
        )
        errors = _validate(s)
        assert any("not in nodes" in e for e in errors)

    def test_undefined_initial_knowledge_service(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 22, "name": "ssh"}],
                }
            },
            entities={"red": {"role": "red"}},
            agents={
                "a1": {
                    "entity": "red",
                    "initial_knowledge": {"services": ["ghost-service"]},
                }
            },
        )
        errors = _validate(s)
        assert any("not in node service names" in e for e in errors)

    def test_undefined_initial_knowledge_account(self):
        s = _make_scenario(
            nodes={"vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}},
            entities={"red": {"role": "red"}},
            accounts={"known-user": {"username": "user", "node": "vm"}},
            agents={
                "a1": {
                    "entity": "red",
                    "initial_knowledge": {"accounts": ["ghost-account"]},
                }
            },
        )
        errors = _validate(s)
        assert any("initial_knowledge account" in e for e in errors)

    def test_allowed_subnet_must_reference_switch_entry(self):
        s = _make_scenario(
            nodes={
                "net": {"type": "switch"},
                "vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            infrastructure={
                "net": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                },
                "vm": {"count": 1, "links": ["net"]},
            },
            entities={"red": {"role": "red"}},
            agents={"a1": {"entity": "red", "allowed_subnets": ["vm"]}},
        )
        errors = _validate(s)
        assert any("allowed_subnet 'vm' must reference a switch/network entry" in e for e in errors)

    def test_initial_knowledge_subnet_must_reference_switch_entry(self):
        s = _make_scenario(
            nodes={
                "net": {"type": "switch"},
                "vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            infrastructure={
                "net": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                },
                "vm": {"count": 1, "links": ["net"]},
            },
            entities={"red": {"role": "red"}},
            agents={"a1": {"entity": "red", "initial_knowledge": {"subnets": ["vm"]}}},
        )
        errors = _validate(s)
        assert any("initial_knowledge subnet 'vm' must reference a switch/network entry" in e for e in errors)

    def test_initial_knowledge_host_must_reference_vm(self):
        s = _make_scenario(
            nodes={"net": {"type": "switch"}},
            infrastructure={
                "net": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                }
            },
            entities={"red": {"role": "red"}},
            agents={"a1": {"entity": "red", "initial_knowledge": {"hosts": ["net"]}}},
        )
        errors = _validate(s)
        assert any("initial_knowledge host 'net' must reference a compute node" in e for e in errors)

    def test_valid_agent(self):
        s = _make_scenario(
            nodes={
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 22, "name": "ssh"}],
                },
                "net": {"type": "switch"},
            },
            infrastructure={"net": {"count": 1, "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}}},
            entities={"red": {"role": "red"}},
            accounts={"hacker": {"username": "h4x", "node": "vm"}},
            agents={
                "a1": {
                    "entity": "red",
                    "actions": ["scan", "exploit"],
                    "starting_accounts": ["hacker"],
                    "allowed_subnets": ["net"],
                    "initial_knowledge": {
                        "hosts": ["vm"],
                        "subnets": ["net"],
                        "services": ["ssh"],
                        "accounts": ["hacker"],
                    },
                }
            },
        )
        errors = _validate(s)
        assert not errors


class TestAgentParticipantFraming:
    """ACT-601 — declarative participant framing fields on Agent.

    Verifies semantic validation for the three framing fields that don't
    already exist on Agent: ``starting_assertions``, ``authority_anchors``,
    ``operating_scope``. Identity and role are already covered by the
    pre-existing ``Agent.entity`` and ``Entity.role`` bindings; the
    ``TestVerifyAgents`` cases above cover those.
    """

    def _base_scenario_kwargs(self) -> dict:
        return {
            "nodes": {
                "vm": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
                "net": {"type": "switch"},
            },
            "infrastructure": {
                "net": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                },
                "vm": {"count": 1, "links": ["net"]},
            },
            "entities": {"red": {"role": "red"}},
            "conditions": {
                "beacon-online": {"command": "/usr/local/bin/check-beacon", "interval": 30},
            },
            "propositions": {
                "beacon-online": {
                    "description": "The governed VM has declared beacon state.",
                    "subjects": ["nodes.vm"],
                    "basis": "declared_state",
                    "predicate": {
                        "kind": "boolean",
                        "property": "beacon-online",
                        "semantic_ref": "urn:raes:declared-property:beacon-online",
                        "operator": "equals",
                        "expected": True,
                    },
                },
            },
            "assertions": {
                "beacon-online": {
                    "proposition": "beacon-online",
                    "role": "precondition",
                    "polarity": "positive",
                },
            },
            "relationships": {
                "red-controls-vm": {
                    "type": "manages",
                    "source": "red",
                    "target": "vm",
                },
            },
        }

    def test_undefined_starting_assertion(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "starting_assertions": ["ghost-condition"],
                },
            },
        )
        errors = _validate(s)
        assert any("assertion 'ghost-condition' not in assertions section" in e for e in errors), errors

    def test_defined_starting_assertion(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "starting_assertions": ["beacon-online"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_starting_assertion_accepts_variable_placeholder(self):
        kwargs = self._base_scenario_kwargs()
        kwargs["variables"] = {"beacon_ref": {"type": "string", "default": "beacon-online"}}
        s = _make_scenario(
            **kwargs,
            agents={
                "a1": {
                    "entity": "red",
                    "starting_assertions": ["${beacon_ref}"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_starting_assertion_rejects_section_qualified_ref(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "starting_assertions": ["assertions.beacon-online"],
                },
            },
        )
        errors = _validate(s)
        assert any("assertion 'assertions.beacon-online' not in assertions section" in e for e in errors), errors

    def test_qualified_starting_assertion_undefined_is_rejected(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "starting_assertions": ["assertions.ghost"],
                },
            },
        )
        errors = _validate(s)
        assert any("assertion 'assertions.ghost' not in assertions section" in e for e in errors), errors

    def test_undefined_authority_anchor(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "authority_anchors": ["ghost-anchor"],
                },
            },
        )
        errors = _validate(s)
        assert any("authority_anchor 'ghost-anchor' does not reference any defined element" in e for e in errors), (
            errors
        )

    def test_defined_authority_anchor_entity(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "authority_anchors": ["red"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_defined_authority_anchor_relationship(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "authority_anchors": ["red-controls-vm"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_authority_anchor_accepts_variable_placeholder(self):
        kwargs = self._base_scenario_kwargs()
        kwargs["variables"] = {"authority_ref": {"type": "string", "default": "red"}}
        s = _make_scenario(
            **kwargs,
            agents={
                "a1": {
                    "entity": "red",
                    "authority_anchors": ["${authority_ref}"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_undefined_operating_scope(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["ghost-scope"],
                },
            },
        )
        errors = _validate(s)
        assert any(
            "operating_scope 'ghost-scope' does not reference any defined targetable element" in e for e in errors
        ), errors

    def test_defined_operating_scope(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["net"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_operating_scope_rejects_non_targetable(self):
        kwargs = self._base_scenario_kwargs()
        kwargs["variables"] = {"flag": {"type": "boolean", "default": True}}
        s = _make_scenario(
            **kwargs,
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["flag"],
                },
            },
        )
        errors = _validate(s)
        assert any("operating_scope 'flag' does not reference any defined targetable element" in e for e in errors), (
            errors
        )

    def test_operating_scope_accepts_variable_placeholder(self):
        kwargs = self._base_scenario_kwargs()
        kwargs["variables"] = {"scope_ref": {"type": "string", "default": "net"}}
        s = _make_scenario(
            **kwargs,
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["${scope_ref}"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_full_participant_framing_agent_validates(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            accounts={"phished": {"username": "u", "node": "vm"}},
            agents={
                "red-agent": {
                    "entity": "red",
                    "starting_accounts": ["phished"],
                    "starting_assertions": ["beacon-online"],
                    "authority_anchors": ["red", "red-controls-vm"],
                    "allowed_subnets": ["net"],
                    "operating_scope": ["net", "vm"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_operating_scope_accepts_service_ref(self):
        kwargs = self._base_scenario_kwargs()
        kwargs["nodes"]["vm"]["services"] = [{"port": 22, "name": "ssh"}]
        s = _make_scenario(
            **kwargs,
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["ssh"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_operating_scope_accepts_content_section(self):
        kwargs = self._base_scenario_kwargs()
        kwargs["content"] = {
            "docs": {
                "type": "dataset",
                "target": "vm",
                "items": [{"name": "playbook"}],
            },
        }
        s = _make_scenario(
            **kwargs,
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["docs", "playbook"],
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_operating_scope_rejects_condition(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["beacon-online"],
                },
            },
        )
        errors = _validate(s)
        assert any(
            "operating_scope 'beacon-online' does not reference any defined targetable element" in e for e in errors
        ), errors

    def test_operating_scope_rejects_relationship(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["red-controls-vm"],
                },
            },
        )
        errors = _validate(s)
        assert any(
            "operating_scope 'red-controls-vm' does not reference any defined targetable element" in e for e in errors
        ), errors

    def test_operating_scope_rejects_account(self):
        kwargs = self._base_scenario_kwargs()
        s = _make_scenario(
            **kwargs,
            accounts={"phished": {"username": "u", "node": "vm"}},
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["phished"],
                },
            },
        )
        errors = _validate(s)
        assert any(
            "operating_scope 'phished' does not reference any defined targetable element" in e for e in errors
        ), errors

    def test_operating_scope_rejects_switch_as_host(self):
        # Switch nodes route through the subnet path (via infrastructure),
        # not the host path. `nodes.<switch>` must NOT validate as a host
        # operating-scope ref.
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["nodes.net"],
                },
            },
        )
        errors = _validate(s)
        assert any(
            "operating_scope 'nodes.net' does not reference any defined targetable element" in e for e in errors
        ), errors

    def test_operating_scope_rejects_vm_as_subnet(self):
        # VM-backed infrastructure entries are reachable through the host
        # path's `nodes.vm` alias, not as a subnet. `infrastructure.vm`
        # must NOT validate as a subnet operating-scope ref.
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["infrastructure.vm"],
                },
            },
        )
        errors = _validate(s)
        assert any(
            "operating_scope 'infrastructure.vm' does not reference any defined targetable element" in e for e in errors
        ), errors

    def test_operating_scope_accepts_qualified_host_and_subnet_refs(self):
        s = _make_scenario(
            **self._base_scenario_kwargs(),
            agents={
                "a1": {
                    "entity": "red",
                    "operating_scope": ["nodes.vm", "infrastructure.net"],
                },
            },
        )
        errors = _validate(s)
        assert not errors


class TestVerifyObjectives:
    def _base_kwargs(self) -> dict:
        return {
            "nodes": {
                "net": {"type": "switch"},
                "web": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            "infrastructure": {
                "net": {
                    "count": 1,
                    "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
                },
                "web": {"count": 1, "links": ["net"]},
            },
            "entities": {
                "red": {"role": "red"},
                "blue": {"role": "blue"},
            },
            "agents": {
                "red-agent": {
                    "entity": "red",
                    "actions": ["Scan", "Exploit"],
                },
            },
            "conditions": {
                "exercise-passed": {"command": "/bin/check", "interval": 30},
            },
            "propositions": {
                "exercise-passed": {
                    "description": "The governed exercise completion state is declared.",
                    "subjects": ["nodes.web"],
                    "basis": "declared_state",
                    "predicate": {
                        "kind": "boolean",
                        "property": "exercise-passed",
                        "semantic_ref": "urn:raes:declared-property:exercise-passed",
                        "operator": "equals",
                        "expected": True,
                    },
                },
            },
            "assertions": {
                "exercise-passed": {
                    "proposition": "exercise-passed",
                    "role": "postcondition",
                    "polarity": "positive",
                },
            },
            "events": {"attack-wave": {}},
            "scripts": {
                "main-timeline": {
                    "start_time": 0,
                    "end_time": 3600,
                    "speed": 1.0,
                    "events": {"attack-wave": 600},
                },
            },
            "stories": {"exercise": {"scripts": ["main-timeline"]}},
        }

    def test_undefined_agent(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "ghost-agent",
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        )
        errors = _validate(s)
        assert any("undefined agent" in e for e in errors)

    def test_undefined_entity(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "entity": "ghost-team",
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        )
        errors = _validate(s)
        assert any("undefined entity" in e for e in errors)

    def test_actions_must_be_declared_by_agent(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "actions": ["Persist"],
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        )
        errors = _validate(s)
        assert any("is not declared by agent" in e for e in errors)

    def test_target_must_resolve(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "targets": ["ghost-target"],
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        )
        errors = _validate(s)
        assert any("defined targetable element" in e for e in errors)

    def test_target_rejects_ambiguous_bare_ref(self):
        kwargs = self._base_kwargs()
        kwargs["features"] = {"web": {"type": "service", "source": {"name": "nginx"}}}
        s = _make_scenario(
            **kwargs,
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "targets": ["web"],
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        )
        errors = _validate(s)
        assert any("target 'web' is ambiguous" in e for e in errors)
        assert any("nodes.web" in e and "features.web" in e for e in errors)

    def test_targets_accept_section_qualified_refs(self):
        kwargs = self._base_kwargs()
        s = _make_scenario(
            **kwargs,
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "targets": ["nodes.web", "infrastructure.net"],
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_targets_can_reference_named_services_and_acls(self):
        kwargs = self._base_kwargs()
        kwargs["nodes"]["web"]["services"] = [{"port": 443, "name": "web-https"}]
        kwargs["infrastructure"]["net"]["acls"] = [
            {
                "name": "allow-admin",
                "direction": "in",
                "from_net": "net",
                "protocol": "tcp",
                "ports": [443],
                "action": "allow",
            }
        ]
        s = _make_scenario(
            **kwargs,
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "targets": [
                        "nodes.web.services.web-https",
                        "infrastructure.net.acls.allow-admin",
                    ],
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
            relationships={
                "r1": {
                    "type": "connects_to",
                    "source": "nodes.web.services.web-https",
                    "target": "infrastructure.net.acls.allow-admin",
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_success_references_must_exist(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "success": {"assertions": ["ghost-condition"]},
                },
            },
        )
        errors = _validate(s)
        assert any("success assertion 'ghost-condition' not in assertions section" in e for e in errors)

    def test_window_event_must_belong_to_script(self):
        kwargs = self._base_kwargs()
        kwargs["events"] = {"attack-wave": {}, "cleanup-wave": {}}
        s = _make_scenario(
            **kwargs,
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "success": {"assertions": ["exercise-passed"]},
                    "window": {
                        "scripts": ["main-timeline"],
                        "events": ["cleanup-wave"],
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("not included by the referenced scripts" in e for e in errors)

    def test_dependency_cycle_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "success": {"assertions": ["exercise-passed"]},
                    "depends_on": ["obj-2"],
                },
                "obj-2": {
                    "entity": "blue",
                    "success": {"assertions": ["exercise-passed"]},
                    "depends_on": ["obj-1"],
                },
            },
        )
        errors = _validate(s)
        assert any("Objective dependency graph contains a cycle" in e for e in errors)

    def test_depends_on_must_reference_defined_objective(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "success": {"assertions": ["exercise-passed"]},
                    "depends_on": ["ghost-objective"],
                },
            },
        )
        errors = _validate(s)
        assert any("depends on undefined objective 'ghost-objective'" in e for e in errors)

    def test_window_steps_require_workflows(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "success": {"assertions": ["exercise-passed"]},
                    "window": {"steps": ["response.validate"]},
                },
            },
        )
        errors = _validate(s)
        assert any("window steps require at least one referenced workflow" in e for e in errors)

    def test_window_steps_must_belong_to_workflow(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "obj-1": {
                    "agent": "red-agent",
                    "success": {"assertions": ["exercise-passed"]},
                    "window": {
                        "workflows": ["response"],
                        "steps": ["other.validate"],
                    },
                },
            },
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "obj-1",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
                "other": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "obj-1",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("is not part of the referenced workflows" in e for e in errors)

    def test_valid_objective(self):
        s = _make_scenario(
            **self._base_kwargs(),
            objectives={
                "recon": {
                    "agent": "red-agent",
                    "actions": ["Scan"],
                    "targets": ["web"],
                    "success": {"assertions": ["exercise-passed"]},
                    "window": {
                        "stories": ["exercise"],
                        "scripts": ["main-timeline"],
                        "events": ["attack-wave"],
                    },
                },
                "report": {
                    "entity": "blue",
                    "success": {"assertions": ["exercise-passed"]},
                    "depends_on": ["recon"],
                },
            },
        )
        errors = _validate(s)
        assert not errors


class TestVerifyWorkflows:
    def _base_kwargs(self) -> dict:
        return {
            "entities": {"blue": {"role": "blue"}},
            "conditions": {
                "exercise-passed": {"command": "/bin/check", "interval": 30},
            },
            "propositions": {
                "exercise-passed": {
                    "description": "The governed exercise completion state is declared.",
                    "subjects": ["entities.blue"],
                    "basis": "declared_state",
                    "predicate": {
                        "kind": "boolean",
                        "property": "exercise-passed",
                        "semantic_ref": "urn:raes:declared-property:exercise-passed",
                        "operator": "equals",
                        "expected": True,
                    },
                },
            },
            "assertions": {
                "exercise-passed": {
                    "proposition": "exercise-passed",
                    "role": "postcondition",
                    "polarity": "positive",
                },
            },
            "objectives": {
                "validate-release": {
                    "entity": "blue",
                    "success": {"assertions": ["exercise-passed"]},
                },
                "rollback-edge": {
                    "entity": "blue",
                    "success": {"assertions": ["exercise-passed"]},
                },
            },
        }

    def test_workflow_references_undefined_objective(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "missing-objective",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("references undefined objective" in e for e in errors)

    def test_workflow_missing_start_step(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("start step 'validate' is not defined" in e for e in errors)

    def test_workflow_cycle_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "parallel",
                            "branches": ["validate", "recover"],
                            "join": "finish",
                        },
                        "recover": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "finish",
                        },
                        "finish": {"type": "join", "next": "validate"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("graph contains a cycle" in e for e in errors)

    def test_workflow_unreachable_step_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                        "orphan": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("contains unreachable steps: orphan" in e for e in errors)

    def test_parallel_branch_reference_must_exist(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback-edge", "missing-step"],
                            "join": "joined",
                        },
                        "rollback-edge": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "finish"},
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("branch step 'missing-step' is not defined" in e for e in errors)

    def test_valid_workflow(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"objectives": ["validate-release"]},
                            "then": "fanout",
                            "else": "finish",
                        },
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "finish"},
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_valid_retry_step(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "retry-flow": {
                    "start": "loop",
                    "steps": {
                        "loop": {
                            "type": "retry",
                            "objective": "validate-release",
                            "on_success": "finish",
                            "max_attempts": 5,
                            "on_exhausted": "recover",
                        },
                        "recover": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_valid_switch_and_call_workflow(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "child": {
                    "start": "run",
                    "steps": {
                        "run": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
                "parent": {
                    "start": "route",
                    "steps": {
                        "route": {
                            "type": "switch",
                            "cases": [
                                {
                                    "when": {"objectives": ["validate-release"]},
                                    "next": "delegate",
                                }
                            ],
                            "default": "finish",
                        },
                        "delegate": {
                            "type": "call",
                            "workflow": "child",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_workflow_call_cycle_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "a": {
                    "start": "delegate",
                    "steps": {
                        "delegate": {
                            "type": "call",
                            "workflow": "b",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
                "b": {
                    "start": "delegate",
                    "steps": {
                        "delegate": {
                            "type": "call",
                            "workflow": "a",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("Workflow call graph contains a cycle" in e for e in errors)

    def test_retry_missing_exhausted_step_ref(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "retry-flow": {
                    "start": "loop",
                    "steps": {
                        "loop": {
                            "type": "retry",
                            "objective": "validate-release",
                            "on_success": "finish",
                            "max_attempts": 3,
                            "on_exhausted": "nonexistent",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("on-exhausted step 'nonexistent' is not defined" in e for e in errors)

    def test_step_state_must_reference_prior_executable_step(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "validate", "outcomes": ["succeeded"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_step_state_undefined_ref(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "missing-step", "outcomes": ["failed"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("references undefined step state 'missing-step'" in e for e in errors)

    def test_step_state_non_causal_ref_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "confirm", "outcomes": ["succeeded"]}]},
                            "then": "confirm",
                            "else": "finish",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("not guaranteed to be known before this predicate" in e for e in errors)

    def test_step_state_self_ref_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "branch",
                    "steps": {
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "branch", "outcomes": ["succeeded"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("cannot reference its own state in a predicate" in e for e in errors)

    def test_step_state_non_executable_ref_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "finish", "outcomes": ["failed"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("cannot reference non-executable step 'finish'" in e for e in errors)

    def test_step_state_decision_ref_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "gate", "outcomes": ["failed"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "gate": {
                            "type": "decision",
                            "when": {"assertions": ["service-restored"]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("cannot reference non-executable step 'gate'" in e for e in errors)

    def test_step_state_impossible_outcome_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "branch",
                        },
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "validate", "outcomes": ["exhausted"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("impossible outcomes" in e for e in errors)

    def test_join_rejects_foreign_predecessors(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "gate",
                    "steps": {
                        "gate": {
                            "type": "decision",
                            "when": {"assertions": ["service-restored"]},
                            "then": "fanout",
                            "else": "joined",
                        },
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "finish"},
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("may only be entered from the owning parallel's branch closure" in e for e in errors)

    def test_parallel_join_must_be_join_step(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "finish",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "finish",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("is used as a parallel join but is not a join step" in e for e in errors)

    def test_parallel_branch_paths_must_converge_on_join(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "finish",
                        },
                        "joined": {"type": "join", "next": "finish"},
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("requires every explicit branch path" in e for e in errors)

    def test_join_step_must_be_referenced(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "finish",
                        },
                        "orphan-join": {"type": "join", "next": "finish"},
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("join step 'orphan-join' is not referenced" in e for e in errors)

    def test_post_join_branch_state_ref_is_allowed(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "branch"},
                        "branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "rollback", "outcomes": ["succeeded"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_post_join_attempt_count_ref_is_allowed_when_guaranteed(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "retry",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                            "max_attempts": 3,
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "branch"},
                        "branch": {
                            "type": "decision",
                            "when": {
                                "steps": [
                                    {
                                        "step": "rollback",
                                        "outcomes": ["succeeded"],
                                        "min_attempts": 2,
                                    }
                                ]
                            },
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not errors

    def test_branch_local_state_ref_before_join_is_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "branch-in-branch",
                        },
                        "branch-in-branch": {
                            "type": "decision",
                            "when": {"steps": [{"step": "confirm", "outcomes": ["succeeded"]}]},
                            "then": "joined",
                            "else": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "finish"},
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("not guaranteed to be known before this predicate" in e for e in errors)

    def test_non_guaranteed_branch_internal_state_ref_after_join_is_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                        },
                        "rollback": {
                            "type": "decision",
                            "when": {"assertions": ["service-restored"]},
                            "then": "rollback-success",
                            "else": "joined",
                        },
                        "rollback-success": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "branch"},
                        "branch": {
                            "type": "decision",
                            "when": {
                                "steps": [
                                    {
                                        "step": "rollback-success",
                                        "outcomes": ["succeeded"],
                                    }
                                ]
                            },
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("not guaranteed to be known before this predicate" in e for e in errors)

    def test_parallel_failure_bypass_does_not_expose_branch_state(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "fanout",
                    "steps": {
                        "fanout": {
                            "type": "parallel",
                            "branches": ["rollback", "confirm"],
                            "join": "joined",
                            "on_failure": "recover",
                        },
                        "rollback": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "on_success": "joined",
                        },
                        "confirm": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "joined",
                        },
                        "joined": {"type": "join", "next": "finish"},
                        "recover": {
                            "type": "decision",
                            "when": {"steps": [{"step": "rollback", "outcomes": ["succeeded"]}]},
                            "then": "finish",
                            "else": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("not guaranteed to be known before this predicate" in e for e in errors)

    def test_on_failure_variable_ref_tolerated(self):
        s = _make_scenario(
            **self._base_kwargs(),
            variables={
                "recovery_step": {"type": "string", "default": "recover"},
            },
            workflows={
                "response": {
                    "start": "validate",
                    "steps": {
                        "validate": {
                            "type": "objective",
                            "objective": "validate-release",
                            "on_success": "finish",
                            "on_failure": "${recovery_step}",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert not any("on-failure" in e for e in errors)

    def test_non_compensable_workflow_step_rejects_compensation_target(self):
        with pytest.raises(ValueError, match="Decision workflow step only supports"):
            _make_scenario(
                **self._base_kwargs(),
                workflows={
                    "response": {
                        "start": "branch",
                        "steps": {
                            "branch": {
                                "type": "decision",
                                "when": {"assertions": ["check"]},
                                "then": "finish",
                                "else": "finish",
                                "compensate_with": "rollback",
                            },
                            "finish": {"type": "end"},
                        },
                    },
                    "rollback": {
                        "start": "finish",
                        "steps": {"finish": {"type": "end"}},
                    },
                },
            )

    def test_workflow_compensation_cycle_is_rejected(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "run",
                    "compensation": {"mode": "automatic", "on": ["failed"]},
                    "steps": {
                        "run": {
                            "type": "objective",
                            "objective": "validate-release",
                            "compensate_with": "rollback",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
                "rollback": {
                    "start": "undo",
                    "steps": {
                        "undo": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "compensate_with": "response",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
            },
        )
        errors = _validate(s)
        assert any("Combined workflow call/compensation graph contains a cycle" in e for e in errors)

    def test_compensation_workflow_cannot_declare_compensate_with_steps(self):
        s = _make_scenario(
            **self._base_kwargs(),
            workflows={
                "response": {
                    "start": "run",
                    "compensation": {"mode": "automatic", "on": ["failed"]},
                    "steps": {
                        "run": {
                            "type": "objective",
                            "objective": "validate-release",
                            "compensate_with": "rollback",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
                "rollback": {
                    "start": "undo",
                    "steps": {
                        "undo": {
                            "type": "objective",
                            "objective": "rollback-edge",
                            "compensate_with": "cleanup",
                            "on_success": "finish",
                        },
                        "finish": {"type": "end"},
                    },
                },
                "cleanup": {
                    "start": "finish",
                    "steps": {"finish": {"type": "end"}},
                },
            },
        )
        errors = _validate(s)
        assert any("cannot be used as a compensation workflow" in e for e in errors)


class TestVerifyVariables:
    def test_defined_variables_allow_placeholders_across_models(self):
        s = _make_scenario(
            variables={
                "ram_bytes": {"type": "integer", "default": 1073741824},
                "cpu_cores": {"type": "integer", "default": 1},
                "node_count": {"type": "integer", "default": 1},
                "network_cidr": {"type": "string", "default": "10.0.0.0/24"},
                "network_gateway": {"type": "string", "default": "10.0.0.1"},
                "is_internal": {"type": "boolean", "default": True},
                "check_interval": {"type": "integer", "default": 30},
                "max_score": {"type": "integer", "default": 10},
                "pass_percentage": {"type": "integer", "default": 75},
                "script_start": {"type": "integer", "default": 0},
                "script_end": {"type": "integer", "default": 3600},
                "script_speed": {"type": "number", "default": 1.0},
                "event_time": {"type": "integer", "default": 600},
                "target_node": {"type": "string", "default": "vm"},
                "subnet_name": {"type": "string", "default": "net"},
                "entity_name": {"type": "string", "default": "blue"},
                "account_name": {"type": "string", "default": "admin"},
                "service_name": {"type": "string", "default": "ssh"},
                "service_port": {"type": "integer", "default": 22},
                "relationship_source": {"type": "string", "default": "web"},
                "relationship_target": {"type": "string", "default": "db"},
                "contains_sensitive_data": {"type": "boolean", "default": False},
                "is_disabled": {"type": "boolean", "default": False},
                "objective_target": {"type": "string", "default": "vm"},
            },
            nodes={
                "net": {"type": "switch"},
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "${ram_bytes}", "cpu": "${cpu_cores}"},
                    "roles": {"admin": {"username": "user", "entities": ["${entity_name}"]}},
                    "services": [{"port": "${service_port}", "name": "ssh"}],
                },
            },
            infrastructure={
                "net": {
                    "count": 1,
                    "properties": {
                        "cidr": "${network_cidr}",
                        "gateway": "${network_gateway}",
                        "internal": "${is_internal}",
                    },
                },
                "vm": {"count": "${node_count}", "links": ["net"]},
            },
            conditions={
                "check": {
                    "command": "/bin/check",
                    "interval": "${check_interval}",
                }
            },
            propositions={
                "check": {
                    "description": "The variable-selected objective target has declared runtime state.",
                    "subjects": ["${objective_target}"],
                    "basis": "declared_state",
                    "predicate": {
                        "kind": "presence",
                        "property": "runtime",
                        "semantic_ref": "urn:raes:declared-property:runtime",
                        "operator": "exists",
                    },
                },
            },
            assertions={
                "check": {
                    "proposition": "check",
                    "role": "postcondition",
                    "polarity": "positive",
                },
            },
            entities={"blue": {"role": "blue"}},
            events={"evt": {}},
            scripts={
                "timeline": {
                    "start_time": "${script_start}",
                    "end_time": "${script_end}",
                    "speed": "${script_speed}",
                    "events": {"evt": "${event_time}"},
                }
            },
            stories={"story": {"speed": "${script_speed}", "scripts": ["timeline"]}},
            content={
                "dataset": {
                    "type": "file",
                    "target": "${target_node}",
                    "path": "/tmp/flag",
                    "sensitive": "${contains_sensitive_data}",
                }
            },
            accounts={
                "admin": {
                    "username": "administrator",
                    "node": "${target_node}",
                    "disabled": "${is_disabled}",
                }
            },
            relationships={
                "r1": {
                    "type": "connects_to",
                    "source": "${relationship_source}",
                    "target": "${relationship_target}",
                }
            },
            agents={
                "a1": {
                    "entity": "${entity_name}",
                    "starting_accounts": ["${account_name}"],
                    "allowed_subnets": ["${subnet_name}"],
                    "initial_knowledge": {
                        "hosts": ["${target_node}"],
                        "subnets": ["${subnet_name}"],
                        "services": ["${service_name}"],
                        "accounts": ["${account_name}"],
                    },
                }
            },
            objectives={
                "obj": {
                    "agent": "a1",
                    "targets": ["${objective_target}"],
                    "success": {"assertions": ["check"]},
                }
            },
        )
        errors = _validate(s)
        assert not errors

    def test_undefined_variable_reference_reported(self):
        s = _make_scenario(
            nodes={"sw": {"type": "switch"}},
            infrastructure={"sw": {"count": "${missing_count}"}},
        )
        errors = _validate(s)
        assert any("Undefined variable 'missing_count'" in e for e in errors)

    def test_embedded_undefined_variable_reference_reported(self):
        s = _make_scenario(description="deploy host-${missing_env}")
        errors = _validate(s)
        assert any("Undefined variable 'missing_env' referenced at 'description'" in e for e in errors)

    def test_embedded_declared_variable_reference_allowed(self):
        s = _make_scenario(
            description="deploy host-${env_name}",
            variables={"env_name": {"type": "string", "default": "lab"}},
        )
        assert not _validate(s)


class TestAdvisories:
    def test_vm_without_resources_emits_advisory(self):
        scenario = _make_scenario(
            nodes={"vm": {"type": "compute"}},
        )
        validator = SemanticValidator(scenario)
        validator.validate()
        assert any("without 'resources'" in warning for warning in validator.warnings)


class TestValidFullScenario:
    def test_complete_scenario_validates(self):
        """A complete scenario passes validation (post ADR-073, no scoring sections)."""
        s = Scenario(
            name="full-test",
            nodes={
                "sw": {"type": "switch"},
                "vm": {
                    "type": "compute",
                    "resources": {"ram": "2 gib", "cpu": 1},
                    "features": {"svc": "admin"},
                    "conditions": {"check": "admin"},
                    "roles": {"admin": {"username": "user"}},
                },
            },
            infrastructure={
                "sw": {"count": 1, "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}},
                "vm": {"count": 1, "links": ["sw"]},
            },
            features={"svc": {"type": "service", "source": {"name": "apache"}}},
            conditions={"check": {"command": "/bin/check", "interval": 30}},
            entities={
                "blue": {"role": "blue"},
            },
        )
        errors = _validate(s)
        assert not errors


class TestVerifyRuntimeApplication:
    def _node_with_application(self, application: dict, **node_extra) -> dict:
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "runtime": {"applications": [application]},
        }
        node.update(node_extra)
        return node

    def test_application_service_ref_resolves(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_application(
                    {"application_id": "app", "service": "http"},
                    services=[{"port": 8080, "name": "http"}],
                ),
            },
        )
        assert _validate(s) == []

    def test_application_service_ref_undefined_is_rejected(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_application({"application_id": "app", "service": "ghost"}),
            },
        )
        errors = _validate(s)
        assert any("references undefined service 'ghost'" in e for e in errors)

    def test_application_qualified_service_ref_resolves(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_application(
                    {"application_id": "app", "service": "nodes.vm.services.http"},
                    services=[{"port": 8080, "name": "http"}],
                ),
            },
        )
        assert _validate(s) == []

    def test_application_qualified_service_ref_other_node_is_rejected(self):
        s = _make_scenario(
            nodes={
                "other": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 8081, "name": "http"}],
                },
                "vm": self._node_with_application(
                    {"application_id": "app", "service": "nodes.other.services.http"},
                    services=[{"port": 8080, "name": "http"}],
                ),
            },
        )
        errors = _validate(s)
        assert any("must reference a service on the same node" in e for e in errors)

    def test_application_service_variable_reference_is_skipped(self):
        s = _make_scenario(
            variables={"svc": {"type": "string", "required": True}},
            nodes={
                "vm": self._node_with_application({"application_id": "app", "service": "${svc}"}),
            },
        )
        assert _validate(s) == []

    def test_route_vulnerability_refs_require_classification_migration(self):
        node = self._node_with_application(
            {
                "application_id": "app",
                "routes": [{"route_id": "route", "path": "/", "vulnerability_refs": ["known"]}],
            }
        )
        with pytest.raises(ValidationError, match="classification migration"):
            _make_scenario(nodes={"web": node})

    def test_route_template_ref_resolves_to_filesystem_inventory(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "runtime": {
                "filesystem_inventory": [{"path": "/app/templates/index.html", "entry_type": "file"}],
                "applications": [
                    {
                        "application_id": "app",
                        "routes": [
                            {
                                "route_id": "r1",
                                "path": "/",
                                "methods": ["GET"],
                                "templates": ["/app/templates/index.html"],
                            }
                        ],
                    }
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        assert _validate(s) == []

    def test_route_template_ref_not_in_inventory_is_rejected(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "runtime": {
                "filesystem_inventory": [{"path": "/app/templates/index.html", "entry_type": "file"}],
                "applications": [
                    {
                        "application_id": "app",
                        "routes": [
                            {
                                "route_id": "r1",
                                "path": "/",
                                "methods": ["GET"],
                                "templates": ["/app/templates/missing.html"],
                            }
                        ],
                    }
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        errors = _validate(s)
        assert any("does not resolve to an observed file" in e for e in errors)

    def test_route_static_asset_ref_resolves_to_filesystem_inventory(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "runtime": {
                "filesystem_inventory": [{"path": "/app/static/style.css", "entry_type": "file"}],
                "applications": [
                    {
                        "application_id": "app",
                        "routes": [
                            {
                                "route_id": "r1",
                                "path": "/",
                                "methods": ["GET"],
                                "static_assets": ["/app/static/style.css"],
                            }
                        ],
                    }
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        assert _validate(s) == []

    def test_route_static_asset_ref_not_in_inventory_is_rejected(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "runtime": {
                "filesystem_inventory": [{"path": "/app/static/style.css", "entry_type": "file"}],
                "applications": [
                    {
                        "application_id": "app",
                        "routes": [
                            {
                                "route_id": "r1",
                                "path": "/",
                                "methods": ["GET"],
                                "static_assets": ["/app/static/missing.css"],
                            }
                        ],
                    }
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        errors = _validate(s)
        assert any("does not resolve to an observed file" in e for e in errors)


class TestVerifyRuntimeFileService:
    def _service(self, **overrides) -> dict:
        service = {
            "file_service_id": "fileshare-smb",
            "service": "smb",
            "protocol": "smb",
            "shares": [{"share_id": "public", "name": "public"}],
            "principals": [{"principal_id": "nobody", "kind": "guest", "name": "nobody"}],
            "access_rules": [],
            "access_observations": [],
        }
        service.update(overrides)
        return service

    def _node(self, service: dict, **node_extra) -> dict:
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 445, "name": "smb"}],
            "runtime": {"file_services": [service]},
        }
        node.update(node_extra)
        return node

    def test_file_service_resolves_with_same_node_service(self):
        s = _make_scenario(nodes={"fs": self._node(self._service())})
        assert _validate(s) == []

    def test_file_service_rejects_unknown_service_ref(self):
        s = _make_scenario(nodes={"fs": self._node(self._service(service="ghost"))})
        errors = _validate(s)
        assert any("ghost" in e and "file" in e.lower() for e in errors)

    def test_file_service_rule_subject_ref_must_resolve(self):
        svc = self._service(
            access_rules=[
                {
                    "rule_id": "bad-rule",
                    "subject_ref": "missing-principal",
                    "resource_ref": "public",
                    "action": "read",
                    "effect": "allow",
                    "basis": "share_config",
                }
            ]
        )
        s = _make_scenario(nodes={"fs": self._node(svc)})
        errors = _validate(s)
        assert any("subject_ref" in e and "missing-principal" in e for e in errors)

    def test_file_service_rule_resource_ref_must_resolve(self):
        svc = self._service(
            access_rules=[
                {
                    "rule_id": "bad-rule",
                    "subject_ref": "nobody",
                    "resource_ref": "ghost-share",
                    "action": "read",
                    "effect": "allow",
                    "basis": "share_config",
                }
            ]
        )
        s = _make_scenario(nodes={"fs": self._node(svc)})
        errors = _validate(s)
        assert any("resource_ref" in e and "ghost-share" in e for e in errors)

    def test_file_service_observation_subject_resource_must_resolve(self):
        svc = self._service(
            access_observations=[
                {
                    "observation_id": "obs1",
                    "subject_ref": "ghost",
                    "resource_ref": "public",
                    "action": "browse",
                    "outcome": "allowed",
                    "basis": "observed_probe",
                }
            ]
        )
        s = _make_scenario(nodes={"fs": self._node(svc)})
        errors = _validate(s)
        # 'guest' and 'anonymous' literals are accepted; 'ghost' is not.
        assert any("subject_ref" in e and "ghost" in e for e in errors)

    def test_file_service_observation_anonymous_subject_is_accepted(self):
        svc = self._service(
            access_observations=[
                {
                    "observation_id": "obs-anon",
                    "subject_ref": "anonymous",
                    "resource_ref": "public",
                    "action": "browse",
                    "outcome": "allowed",
                    "basis": "observed_probe",
                }
            ]
        )
        s = _make_scenario(nodes={"fs": self._node(svc)})
        assert _validate(s) == []

    def test_file_service_local_user_ref_resolves_against_local_identity(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "service_account",
                    "name": "svc-fileshare",
                    "local_user_ref": "missing-user",
                }
            ]
        )
        node = self._node(svc)
        node["runtime"]["local_identity"] = {
            "users": [{"username": "real-user", "uid": 1100}],
        }
        s = _make_scenario(nodes={"fs": node})
        errors = _validate(s)
        assert any("local_user_ref" in e and "missing-user" in e for e in errors)

    def test_file_service_local_user_ref_passes_when_present(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "service_account",
                    "name": "svc-fileshare",
                    "local_user_ref": "real-user",
                }
            ]
        )
        node = self._node(svc)
        node["runtime"]["local_identity"] = {
            "users": [{"username": "real-user", "uid": 1100}],
        }
        s = _make_scenario(nodes={"fs": node})
        assert _validate(s) == []

    def _ad_node(self) -> dict:
        return {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 389, "name": "ldap"}],
            "runtime": {
                "identity_authorities": [
                    {
                        "identity_authority_id": "techvault-domain",
                        "kind": "domain",
                        "name": "TechVault Domain",
                        "services": [
                            {
                                "service_id": "ldap-endpoint",
                                "service": "ldap",
                                "protocol": "LDAP",
                            }
                        ],
                        "subjects": [
                            {"subject_id": "alice", "kind": "user", "name": "alice"},
                        ],
                    }
                ]
            },
        }

    def test_file_service_directory_subject_ref_resolves_against_identity_authority(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "user",
                    "name": "svc-fileshare",
                    "directory_subject_ref": ("nodes.ad.runtime.identity_authorities.techvault-domain.subjects.alice"),
                }
            ]
        )
        s = _make_scenario(
            nodes={
                "fs": self._node(svc),
                "ad": self._ad_node(),
            }
        )
        assert _validate(s) == []

    def test_file_service_directory_subject_ref_rejects_missing_subject(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "user",
                    "name": "svc-fileshare",
                    "directory_subject_ref": ("nodes.ad.runtime.identity_authorities.techvault-domain.subjects.ghost"),
                }
            ]
        )
        s = _make_scenario(
            nodes={
                "fs": self._node(svc),
                "ad": self._ad_node(),
            }
        )
        errors = _validate(s)
        assert any("directory_subject_ref" in e and "ghost" in e and "does not resolve" in e for e in errors)

    def test_file_service_directory_subject_ref_rejects_missing_authority(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "user",
                    "name": "svc-fileshare",
                    "directory_subject_ref": ("nodes.ad.runtime.identity_authorities.missing.subjects.alice"),
                }
            ]
        )
        s = _make_scenario(
            nodes={
                "fs": self._node(svc),
                "ad": self._ad_node(),
            }
        )
        errors = _validate(s)
        assert any("directory_subject_ref" in e and "missing" in e and "does not resolve" in e for e in errors)

    def test_file_service_directory_subject_ref_rejects_unqualified(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "user",
                    "name": "svc-fileshare",
                    "directory_subject_ref": "bare-alice",
                }
            ]
        )
        s = _make_scenario(nodes={"fs": self._node(svc)})
        errors = _validate(s)
        assert any("directory_subject_ref" in e and "must be a qualified" in e for e in errors)

    def test_file_service_directory_subject_ref_skips_variable(self):
        svc = self._service(
            principals=[
                {
                    "principal_id": "svc-fileshare",
                    "kind": "user",
                    "name": "svc-fileshare",
                    "directory_subject_ref": "${external_subject}",
                }
            ]
        )
        s = _make_scenario(
            variables={"external_subject": {"type": "string", "required": True}},
            nodes={"fs": self._node(svc)},
        )
        assert _validate(s) == []


class TestVerifyRuntimeDatabaseServices:
    def _node_with_db(self, **dbsvc_overrides):
        dbsvc = {
            "database_service_id": "tv-pg",
            "service": "pg",
            "engine": "postgresql",
            "protocol": "postgresql",
            "databases": [
                {
                    "database_id": "tv-db",
                    "name": "techvault",
                    "schemas": [
                        {"schema_id": "pub", "name": "public", "tables": [{"table_id": "users", "name": "users"}]}
                    ],
                }
            ],
            "roles": [{"role_id": "app", "name": "techvault", "role_type": "application"}],
        }
        dbsvc.update(dbsvc_overrides)
        return {
            "type": "compute",
            "services": [{"port": 5432, "name": "pg"}],
            "runtime": {"database_services": [dbsvc]},
        }

    def test_database_service_with_same_node_service_is_valid(self):
        s = _make_scenario(nodes={"db": self._node_with_db()})
        assert _validate(s) == []

    def test_database_service_qualified_same_node_ref_is_valid(self):
        s = _make_scenario(nodes={"db": self._node_with_db(service="nodes.db.services.pg")})
        assert _validate(s) == []

    def test_database_service_owning_service_must_be_same_node(self):
        node = self._node_with_db(service="nodes.other.services.pg")
        s = _make_scenario(
            nodes={
                "db": node,
                "other": {"type": "compute", "services": [{"port": 5432, "name": "pg"}]},
            }
        )
        errors = _validate(s)
        assert any("must reference a service on the same node" in e for e in errors)

    def test_database_service_undefined_owning_service_rejected(self):
        s = _make_scenario(nodes={"db": self._node_with_db(service="ghost")})
        errors = _validate(s)
        assert any("references undefined service 'ghost'" in e for e in errors)

    def test_grant_with_resolvable_refs_is_valid(self):
        s = _make_scenario(
            nodes={
                "db": self._node_with_db(
                    grants=[
                        {
                            "grantee_role_ref": "app",
                            "object_type": "table",
                            "object_ref": "users",
                            "privileges": ["SELECT"],
                        }
                    ]
                )
            }
        )
        assert _validate(s) == []

    def test_grant_grantee_role_ref_must_resolve(self):
        s = _make_scenario(
            nodes={
                "db": self._node_with_db(
                    grants=[
                        {
                            "grantee_role_ref": "ghost",
                            "object_type": "table",
                            "object_ref": "users",
                            "privileges": ["SELECT"],
                        }
                    ]
                )
            }
        )
        errors = _validate(s)
        assert any("grant grantee_role_ref 'ghost' is not a role" in e for e in errors)

    def test_grant_object_ref_must_match_object_type(self):
        s = _make_scenario(
            nodes={
                "db": self._node_with_db(
                    grants=[
                        {
                            "grantee_role_ref": "app",
                            "object_type": "database",
                            "object_ref": "users",
                            "privileges": ["SELECT"],
                        }
                    ]
                )
            }
        )
        errors = _validate(s)
        assert any("grant object_ref 'users' is not a database" in e for e in errors)


class TestVerifyRuntimeDnsServices:
    def _node_with_dns(self, **dns_overrides):
        dns_service = {
            "dns_service_id": "techvault-dns",
            "service": "dns",
            "implementation": "bind",
            "roles": ["authoritative"],
            "configuration_file_refs": ["/etc/bind/named.conf"],
            "zones": [
                {
                    "zone_id": "techvault-local",
                    "name": "techvault.local.",
                    "zone_file_refs": ["/etc/bind/db.techvault.local"],
                    "rrsets": [
                        {
                            "rrset_id": "web-a",
                            "owner": "web.techvault.local.",
                            "record_type": "a",
                            "ttl": 300,
                            "records": [{"address": "172.20.10.20"}],
                        }
                    ],
                }
            ],
        }
        dns_service.update(dns_overrides)
        return {
            "type": "compute",
            "services": [{"port": 53, "protocol": "udp", "name": "dns"}],
            "runtime": {
                "filesystem_inventory": [
                    {"path": "/etc/bind/named.conf", "entry_type": "file"},
                    {"path": "/etc/bind/db.techvault.local", "entry_type": "file"},
                ],
                "dns_services": [dns_service],
            },
        }

    def test_dns_service_with_same_node_service_is_valid(self):
        s = _make_scenario(nodes={"dns": self._node_with_dns()})
        assert _validate(s) == []

    def test_dns_service_qualified_same_node_ref_is_valid(self):
        s = _make_scenario(nodes={"dns": self._node_with_dns(service="nodes.dns.services.dns")})
        assert _validate(s) == []

    def test_dns_service_owning_service_must_be_same_node(self):
        node = self._node_with_dns(service="nodes.other.services.dns")
        s = _make_scenario(
            nodes={
                "dns": node,
                "other": {"type": "compute", "services": [{"port": 53, "protocol": "udp", "name": "dns"}]},
            }
        )
        errors = _validate(s)
        assert any("must reference a service on the same node" in e for e in errors)

    def test_dns_service_undefined_owning_service_rejected(self):
        s = _make_scenario(nodes={"dns": self._node_with_dns(service="ghost")})
        errors = _validate(s)
        assert any("references undefined service 'ghost'" in e for e in errors)

    def test_dns_file_refs_resolve_to_runtime_filesystem_inventory_when_present(self):
        node = self._node_with_dns(configuration_file_refs=["/etc/bind/missing.conf"])
        s = _make_scenario(nodes={"dns": node})
        errors = _validate(s)
        assert any("configuration_file_refs ref '/etc/bind/missing.conf' does not resolve" in e for e in errors)

    def test_relationship_target_to_dns_service_zone_and_rrset_is_valid(self):
        s = _make_scenario(
            nodes={
                "dns": self._node_with_dns(),
                "client": {"type": "compute", "services": [{"port": 443, "name": "https"}]},
            },
            relationships={
                "client-uses-dns": {
                    "type": "connects_to",
                    "source": "nodes.client",
                    "target": "nodes.dns.runtime.dns_services.techvault-dns",
                },
                "zone-authority": {
                    "type": "depends_on",
                    "source": "nodes.dns.runtime.dns_services.techvault-dns",
                    "target": "nodes.dns.runtime.dns_services.techvault-dns.zones.techvault-local",
                },
                "web-record": {
                    "type": "depends_on",
                    "source": "nodes.dns.runtime.dns_services.techvault-dns.zones.techvault-local",
                    "target": "nodes.dns.runtime.dns_services.techvault-dns.zones.techvault-local.rrsets.web-a",
                },
            },
        )
        assert _validate(s) == []


class TestVerifyRelationshipDatabaseAccess:
    def _scenario_with_app_and_db(self, **rel_overrides):
        rel = {
            "type": "connects_to",
            "source": "nodes.web.runtime.applications.webapp",
            "target": "nodes.db.runtime.database_services.tv-pg",
            "database_access": {"role_ref": "app", "auth_method": "scram_sha_256"},
        }
        rel.update(rel_overrides)
        return _make_scenario(
            nodes={
                "db": {
                    "type": "compute",
                    "services": [{"port": 5432, "name": "pg"}],
                    "runtime": {
                        "database_services": [
                            {
                                "database_service_id": "tv-pg",
                                "service": "pg",
                                "engine": "postgresql",
                                "protocol": "postgresql",
                                "databases": [{"database_id": "tv-db", "name": "techvault"}],
                                "roles": [{"role_id": "app", "name": "techvault"}],
                            }
                        ]
                    },
                },
                "web": {
                    "type": "compute",
                    "services": [{"port": 8080, "name": "http"}],
                    "runtime": {"applications": [{"application_id": "webapp", "service": "http"}]},
                },
            },
            relationships={"webapp-to-db": rel},
        )

    def test_relationship_to_database_with_role_is_valid(self):
        # Implicitly exercises the named-ref index for the application source
        # and database target — the strict ``== []`` assertion catches both
        # 'ref didn't resolve' and 'database-access check broke' regressions.
        assert _validate(self._scenario_with_app_and_db()) == []

    def test_relationship_target_to_logical_database_ref_is_valid(self):
        s = self._scenario_with_app_and_db(target="nodes.db.runtime.database_services.tv-pg.databases.tv-db")
        assert _validate(s) == []

    def test_database_access_target_must_resolve_to_database(self):
        s = self._scenario_with_app_and_db(target="nodes.web.runtime.applications.webapp")
        errors = _validate(s)
        assert any("does not resolve to a database service or database" in e for e in errors)

    def test_database_access_role_ref_must_be_a_role_in_the_service(self):
        s = self._scenario_with_app_and_db(database_access={"role_ref": "ghost", "auth_method": "password"})
        errors = _validate(s)
        assert any("role_ref 'ghost' is not a role in database service 'tv-pg'" in e for e in errors)

    def test_database_access_source_must_be_a_runtime_application(self):
        # A defined non-application scenario element (a node) passes generic
        # relationship validation but is not a valid database_access source.
        s = self._scenario_with_app_and_db(source="nodes.db")
        errors = _validate(s)
        assert any("source 'nodes.db' does not resolve to a runtime application" in e for e in errors)

    def test_database_access_variable_source_is_skipped(self):
        # An unresolved ${var} source is left for instantiation, not flagged.
        s = self._scenario_with_app_and_db(source="${app_ref}")
        assert not any("does not resolve to a runtime application" in e for e in _validate(s))


class TestVerifyRelationshipServiceIntegration:
    def _scenario_with_platforms(
        self,
        auth_principal_ref: str = "cortex-api-user",
        *,
        engine_authorization_ref: str | None = "cortex-auth",
    ) -> Scenario:
        engine_application = {
            "platform_application_id": "cortex",
            "service": "api",
            "platform_kind": "analyzer_engine",
            "execution_policy": {"policy_id": "exec"},
            "content_objects": [{"content_object_id": "analyzer", "kind": "analyzer"}],
        }
        if engine_authorization_ref is not None:
            engine_application["authorization_ref"] = engine_authorization_ref
        return _make_scenario(
            nodes={
                "thehive": {
                    "type": "compute",
                    "services": [{"port": 9000, "name": "api"}],
                    "runtime": {
                        "platform_applications": [
                            {
                                "platform_application_id": "thehive",
                                "service": "api",
                                "platform_kind": "case_management",
                                "content_objects": [
                                    {"content_object_id": "case-template", "kind": "case_template"},
                                    {"content_object_id": "custom-field", "kind": "custom_field"},
                                ],
                            }
                        ]
                    },
                },
                "cortex": {
                    "type": "compute",
                    "services": [{"port": 9001, "name": "api"}],
                    "runtime": {
                        "app_authorizations": [
                            {
                                "app_authorization_id": "cortex-auth",
                                "resource_vocabulary": "app_resource",
                                "principals": [{"principal_id": "cortex-api-user"}],
                                "roles": [{"role_id": "api-role"}],
                                "permission_grants": [
                                    {
                                        "grant_id": "api-grant",
                                        "role_ref": "api-role",
                                        "resource_kind": "app_resource",
                                    }
                                ],
                            },
                            {
                                "app_authorization_id": "unrelated-auth",
                                "resource_vocabulary": "app_resource",
                                "principals": [{"principal_id": "wrong-store-principal"}],
                                "roles": [{"role_id": "other-role"}],
                                "permission_grants": [
                                    {
                                        "grant_id": "other-grant",
                                        "role_ref": "other-role",
                                        "resource_kind": "app_resource",
                                    }
                                ],
                            },
                        ],
                        "platform_applications": [engine_application],
                    },
                },
            },
            relationships={
                "thehive-to-cortex": {
                    "type": "connects_to",
                    "source": "nodes.thehive.runtime.platform_applications.thehive",
                    "target": "nodes.cortex.runtime.platform_applications.cortex",
                    "service_integration": {
                        "consumer_ref": "thehive",
                        "engine_ref": "cortex",
                        "integration_kind": "analyzer",
                        "auth_principal_ref": auth_principal_ref,
                    },
                }
            },
        )

    def test_service_integration_auth_principal_resolves_in_engine_authorization(self):
        assert _validate(self._scenario_with_platforms()) == []

    def test_service_integration_auth_principal_must_be_in_engine_authorization(self):
        errors = _validate(self._scenario_with_platforms(auth_principal_ref="wrong-store-principal"))
        assert any("authorization 'cortex-auth'" in error and "wrong-store-principal" in error for error in errors)

    def test_service_integration_auth_principal_uses_any_engine_authorization_when_unset(self):
        s = self._scenario_with_platforms(
            auth_principal_ref="wrong-store-principal",
            engine_authorization_ref=None,
        )
        assert _validate(s) == []


class TestVerifyRelationshipProxyUpstream:
    def _scenario_with_proxy(
        self,
        *,
        route_upstream: dict | None = None,
        proxy_upstream: dict | None = None,
        proxy_node_name: str = "proxy",
        backend_node_name: str = "backend",
        relationship_target: str = "backend",
    ) -> Scenario:
        route = {"route_id": "root", "path": "/", "methods": ["GET"]}
        if route_upstream is not None:
            route["upstream_target"] = route_upstream
        upstream = {"route_ref": "root", "upstream_node_ref": backend_node_name, "upstream_service_ref": "app"}
        if proxy_upstream is not None:
            upstream.update(proxy_upstream)
        return _make_scenario(
            nodes={
                proxy_node_name: {
                    "type": "compute",
                    "services": [{"port": 443, "name": "https"}],
                    "runtime": {
                        "applications": [
                            {
                                "application_id": "nginx",
                                "service": "https",
                                "routes": [route],
                            }
                        ]
                    },
                },
                backend_node_name: {
                    "type": "compute",
                    "services": [{"port": 8080, "name": "app"}],
                },
            },
            relationships={
                "proxy-to-backend": {
                    "type": "connects_to",
                    "source": f"nodes.{proxy_node_name}.runtime.applications.nginx",
                    "target": relationship_target,
                    "proxy_upstream": upstream,
                }
            },
        )

    def test_proxy_upstream_service_ref_must_resolve_on_upstream_node(self):
        errors = _validate(self._scenario_with_proxy(proxy_upstream={"upstream_service_ref": "ghost"}))
        assert any("upstream_service_ref 'ghost'" in error and "backend" in error for error in errors)

    def test_route_upstream_target_service_ref_must_resolve(self):
        errors = _validate(
            self._scenario_with_proxy(
                route_upstream={"target_node_ref": "backend", "target_service": "ghost"},
            )
        )
        assert any("target_service 'ghost'" in error and "backend" in error for error in errors)

    def test_route_upstream_target_service_ref_must_match_target_node_ref(self):
        errors = _validate(
            self._scenario_with_proxy(
                route_upstream={
                    "target_node_ref": "backend",
                    "target_service": "nodes.proxy.services.https",
                },
            )
        )
        assert any("target_service 'nodes.proxy.services.https'" in error and "backend" in error for error in errors)

    def test_proxy_upstream_service_ref_uses_qualified_relationship_target_node(self):
        s = self._scenario_with_proxy(
            relationship_target="nodes.backend.services.app",
            proxy_upstream={"upstream_node_ref": ""},
        )
        assert _validate(s) == []

    def test_proxy_upstream_service_ref_must_match_upstream_node_ref(self):
        errors = _validate(
            self._scenario_with_proxy(
                proxy_upstream={"upstream_service_ref": "nodes.proxy.services.https"},
            )
        )
        assert any(
            "upstream_service_ref 'nodes.proxy.services.https'" in error and "backend" in error for error in errors
        )

    def test_proxy_upstream_invalid_upstream_node_ref_is_reported(self):
        errors = _validate(
            self._scenario_with_proxy(
                proxy_upstream={"upstream_node_ref": "ghost"},
            )
        )
        assert any("upstream_node_ref 'ghost'" in error and "defined node" in error for error in errors)

    def test_proxy_upstream_agreement_uses_relationship_target_for_service_refs(self):
        s = self._scenario_with_proxy(
            route_upstream={
                "target_service": "nodes.backend.services.app",
                "tls_terminated_here": True,
            },
            proxy_upstream={
                "upstream_node_ref": "",
                "upstream_service_ref": "app",
                "client_tls_terminated": True,
            },
            relationship_target="nodes.backend.services.app",
        )
        assert _validate(s) == []

    def test_proxy_upstream_agreement_accepts_bare_and_qualified_service_refs(self):
        s = self._scenario_with_proxy(
            route_upstream={
                "target_node_ref": "backend",
                "target_service": "nodes.backend.services.app",
                "tls_terminated_here": True,
            },
            proxy_upstream={"upstream_service_ref": "app", "client_tls_terminated": True},
        )
        assert _validate(s) == []

    def test_proxy_upstream_rejects_dotted_authored_node_names(self):
        with pytest.raises(ValidationError, match="nodes declaration key must be a portable SDL identifier"):
            self._scenario_with_proxy(
                proxy_node_name="front.proxy",
                backend_node_name="app.backend",
            )


# ---------------------------------------------------------------------------
# Runtime SSH server configuration semantics (ADR-031)
# ---------------------------------------------------------------------------


class TestVerifyRuntimeSshServer:
    def _node_with_ssh_server(self, ssh_server: dict, **node_extra) -> dict:
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "runtime": {"ssh_servers": [ssh_server]},
        }
        node.update(node_extra)
        return node

    def test_bare_service_ref_resolves(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_ssh_server(
                    {"ssh_server_id": "sshd-default", "service": "ssh"},
                    services=[{"port": 22, "name": "ssh"}],
                ),
            },
        )
        assert _validate(s) == []

    def test_undefined_service_ref_rejected(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_ssh_server(
                    {"ssh_server_id": "sshd-default", "service": "ghost"},
                ),
            },
        )
        errors = _validate(s)
        assert any("references undefined service 'ghost'" in e for e in errors)

    def test_qualified_service_ref_same_node_resolves(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_ssh_server(
                    {"ssh_server_id": "sshd-default", "service": "nodes.vm.services.ssh"},
                    services=[{"port": 22, "name": "ssh"}],
                ),
            },
        )
        assert _validate(s) == []

    def test_qualified_service_ref_other_node_rejected(self):
        s = _make_scenario(
            nodes={
                "other": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 2222, "name": "ssh"}],
                },
                "vm": self._node_with_ssh_server(
                    {"ssh_server_id": "sshd-default", "service": "nodes.other.services.ssh"},
                    services=[{"port": 22, "name": "ssh"}],
                ),
            },
        )
        errors = _validate(s)
        assert any("must reference a service on the same node" in e for e in errors)

    def test_malformed_qualified_service_ref_rejected(self):
        s = _make_scenario(
            nodes={
                "vm": self._node_with_ssh_server(
                    {"ssh_server_id": "sshd-default", "service": "nodes.vm.svc.ssh"},
                ),
            },
        )
        errors = _validate(s)
        assert any("must be a bare service name" in e for e in errors)

    def test_service_variable_reference_skipped(self):
        s = _make_scenario(
            variables={"svc": {"type": "string", "required": True}},
            nodes={
                "vm": self._node_with_ssh_server(
                    {"ssh_server_id": "sshd-default", "service": "${svc}"},
                ),
            },
        )
        assert _validate(s) == []

    def test_local_user_criterion_present_in_inventory_passes(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 22, "name": "ssh"}],
            "runtime": {
                "local_identity": {
                    "users": [{"username": "kali", "uid": 1000}],
                },
                "ssh_servers": [
                    {
                        "ssh_server_id": "sshd-default",
                        "service": "ssh",
                        "match_rules": [
                            {
                                "match_id": "m-kali",
                                "criteria": [{"kind": "local_user", "pattern": "kali"}],
                            },
                        ],
                    },
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        assert _validate(s) == []

    def test_local_user_criterion_absent_from_populated_inventory_rejected(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 22, "name": "ssh"}],
            "runtime": {
                "local_identity": {
                    "users": [{"username": "kali", "uid": 1000}],
                },
                "ssh_servers": [
                    {
                        "ssh_server_id": "sshd-default",
                        "service": "ssh",
                        "match_rules": [
                            {
                                "match_id": "m-ghost",
                                "criteria": [{"kind": "local_user", "pattern": "ghost"}],
                            },
                        ],
                    },
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        errors = _validate(s)
        assert any("local user 'ghost'" in e for e in errors)

    def test_local_user_criterion_without_inventory_does_not_error(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 22, "name": "ssh"}],
            "runtime": {
                "ssh_servers": [
                    {
                        "ssh_server_id": "sshd-default",
                        "service": "ssh",
                        "match_rules": [
                            {
                                "match_id": "m-kali",
                                "criteria": [{"kind": "local_user", "pattern": "kali"}],
                            },
                        ],
                    },
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        assert _validate(s) == []

    def test_user_pattern_criterion_not_checked_against_inventory(self):
        """USER (not LOCAL_USER) is a pattern, not an identity — not cross-checked."""
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 22, "name": "ssh"}],
            "runtime": {
                "local_identity": {"users": [{"username": "kali", "uid": 1000}]},
                "ssh_servers": [
                    {
                        "ssh_server_id": "sshd-default",
                        "service": "ssh",
                        "match_rules": [
                            {
                                "match_id": "m-pattern",
                                "criteria": [{"kind": "user", "pattern": "ghost"}],
                            },
                        ],
                    },
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        assert _validate(s) == []

    def test_local_user_wildcard_pattern_not_checked_against_inventory(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 22, "name": "ssh"}],
            "runtime": {
                "local_identity": {"users": [{"username": "kali", "uid": 1000}]},
                "ssh_servers": [
                    {
                        "ssh_server_id": "sshd-default",
                        "service": "ssh",
                        "match_rules": [
                            {
                                "match_id": "m-glob",
                                "criteria": [{"kind": "local_user", "pattern": "ka*"}],
                            },
                        ],
                    },
                ],
            },
        }
        s = _make_scenario(nodes={"vm": node})
        assert _validate(s) == []

    def test_local_user_variable_ref_pattern_skipped(self):
        node = {
            "type": "compute",
            "resources": {"ram": "1 gib", "cpu": 1},
            "services": [{"port": 22, "name": "ssh"}],
            "runtime": {
                "local_identity": {"users": [{"username": "kali", "uid": 1000}]},
                "ssh_servers": [
                    {
                        "ssh_server_id": "sshd-default",
                        "service": "ssh",
                        "match_rules": [
                            {
                                "match_id": "m-var",
                                "criteria": [{"kind": "local_user", "pattern": "${ssh_user}"}],
                            },
                        ],
                    },
                ],
            },
        }
        s = _make_scenario(
            variables={"ssh_user": {"type": "string", "required": True}},
            nodes={"vm": node},
        )
        assert _validate(s) == []
