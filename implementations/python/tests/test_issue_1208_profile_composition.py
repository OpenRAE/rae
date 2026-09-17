"""Imported selections retain exact owners and governed references."""

import pytest
import yaml
from raes import parse_sdl_file
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.profile_selections import authored_resource_profiles
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from test_issue_1208_profile_selections import _account_profile


@pytest.mark.parametrize("omit_defaults", [False, True])
@pytest.mark.parametrize("namespaces", [("shared",), ("first_copy", "second_copy")])
def test_imported_provisioning_profiles_keep_owners_and_mailbox_join(tmp_path, namespaces, omit_defaults):
    selections = {}
    for name, context, address, value in (
        ("account", "account-materialization", "provision.account.admin", None),
        ("content", "service-materialization", "provision.content.seed", {"format": "private"}),
        ("artifact", "artifact-generation", "provision.generated-artifact.digest", {"seed": "public"}),
        ("domain", "identity-domain", "provision.domain-controller.corp.mail", {"realm": "private"}),
    ):
        binding, _ = _account_profile(profile_context=context, address=address, value=value)
        selections[name] = binding.model_copy(update={"binding_id": name}).model_dump(
            mode="json", exclude_defaults=omit_defaults
        )
    source = {
        "name": "profile-module",
        "nodes": {
            "mail": {
                "type": "compute",
                "runtime": {
                    "mail_services": [
                        {
                            "mail_service_id": "mail",
                            "mailboxes": [
                                {"mailbox_id": "admin", "address": "admin@example.test", "account_ref": "admin"}
                            ],
                        }
                    ]
                },
            }
        },
        "accounts": {"admin": {"node": "mail", "username": "admin", "materialization_profile": selections["account"]}},
        "content": {
            "seed": {
                "type": "file",
                "path": "/seed",
                "target": "mail",
                "service_materialization": selections["content"],
            }
        },
        "generated_artifacts": {
            "digest": {
                "generator": selections["artifact"],
                "lifecycle": "reuse_valid",
                "provenance": "urn:example:digest",
                "outputs": [{"name": "public", "path": "digest", "sensitivity": "public"}],
                "consumers": [
                    {
                        "node": "mail",
                        "mount_destination": "/digest",
                        "access_mode": "read_only",
                        "selected_outputs": ["public"],
                    }
                ],
            }
        },
        "identity_domains": {"corp": {"profile": selections["domain"], "authority_account_ref": "admin"}},
        "relationships": {
            "controller": {"type": "domain_controller_for", "source": "mail", "target": "corp", "domain_controller": {}}
        },
    }
    source["module"] = {
        "id": "example/profiles",
        "version": "1.0.0",
        "exports": {k: list(v) for k, v in source.items() if isinstance(v, dict)},
    }
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(source))
    (tmp_path / "root.yaml").write_text(
        yaml.safe_dump({"name": "root", "imports": [{"path": "module.yaml", "namespace": n} for n in namespaces]})
    )
    expanded = parse_sdl_file(tmp_path / "root.yaml")
    prefix = namespaces[0]
    account = expanded.accounts[f"{prefix}.admin"].materialization_profile
    assert account.value["mailbox_ref"] == f"nodes.{prefix}.mail.runtime.mail_services.mail.mailboxes.admin"
    assert expanded.nodes[f"{prefix}.mail"].runtime.mail_services[0].mailboxes[0].account_ref == f"{prefix}.admin"
    execution = plan(compile_runtime_model(expanded), create_stub_manifest())
    bindings = authored_resource_profiles(execution.provisioning.resources.values())
    assert len(bindings) == 4 * len(namespaces)
    assert {b.owner.canonical_address for b in bindings} == {
        address
        for namespace in namespaces
        for address in (
            f"#/resources/provision.account.{namespace}.admin",
            f"#/resources/provision.content.{namespace}.seed",
            f"#/resources/provision.generated-artifact.{namespace}.digest",
            f"#/resources/provision.domain-controller.{namespace}.corp.{namespace}.mail",
        )
    }
    assert expanded.content[f"{prefix}.seed"].service_materialization.value == {"format": "private"}


@pytest.mark.parametrize(
    "section,trail",
    [
        ("identity_facades", ("protocol",)),
        ("relationships", ("forest_trust", "trust_type")),
        ("relationships", ("identity_federation", "protocol")),
        ("relationships", ("identity_federation", "mapping_intent")),
        ("agents", ("interactive_access", "console", "channel")),
    ],
)
@pytest.mark.parametrize("omit_defaults", [False, True])
def test_descriptor_bindings_use_canonical_rewrite_and_preserve_opaque_values(section, trail, omit_defaults):
    from raes._module_symbols import HASHMAP_SECTIONS
    from raes.composition._expand import _rewrite_payload_with_symbols

    binding, _ = _account_profile(value={"opaque": "nodes.mail"})
    raw = binding.model_dump(mode="json", exclude_defaults=omit_defaults)
    raw["owner"]["canonical_address"] = f"#/{section}/owner/" + "/".join(trail)
    child = binding.model_copy(
        update={
            "binding_id": "child",
            "owner": binding.owner.model_copy(update={"canonical_address": raw["owner"]["canonical_address"]}),
        }
    ).model_dump(mode="json", exclude_defaults=omit_defaults)
    raw["children"] = [child]
    value = raw
    for field in reversed(trail):
        value = {field: value}
    payload = {section: {"owner": value}}
    symbols = {key: {} for key in HASHMAP_SECTIONS}
    symbols.update(named={}, targetable=set())
    symbols[section] = {"owner": "shared.owner"}
    result = _rewrite_payload_with_symbols(payload, symbols=symbols, namespace="shared")
    selected = result[section]["shared.owner"]
    for field in trail:
        selected = selected[field]
    expected = f"#/{section}/shared.owner/" + "/".join(trail)
    assert selected["owner"]["canonical_address"] == expected
    assert selected["children"][0]["owner"]["canonical_address"] == expected
    assert selected["value"] == {"opaque": "nodes.mail"}
    assert selected["coordinate"] == raw["coordinate"]


@pytest.mark.parametrize("omit_defaults", [False, True])
def test_imported_fixture_mailbox_reaches_its_exact_authorized_sink(tmp_path, omit_defaults):
    from raes_contracts.account_materialization import ACCOUNT_MAILBOX_SEMANTICS
    from raes_reference_backend import create_reference_backend_target
    from raes_reference_backend.mailbox_materialization import InProcessMailboxSink
    from raes_runtime.manager import RuntimeManager
    from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, _account_payload

    binding, context = _account_profile(ACCOUNT_MAILBOX_SEMANTICS)
    account = _account_payload()
    account.update(node="mail", materialization_profile=binding.model_dump(mode="json", exclude_defaults=omit_defaults))
    source = {
        "name": "mail-module",
        "module": {"id": "example/mail", "version": "1.0.0", "exports": {"nodes": ["mail"], "accounts": ["admin"]}},
        "accounts": {"admin": account},
        "nodes": {
            "mail": {
                "type": "compute",
                "runtime": {
                    "mail_services": [
                        {
                            "mail_service_id": "mail",
                            "mailboxes": [
                                {
                                    "mailbox_id": "admin",
                                    "address": "admin@example.test",
                                    "account_ref": "admin",
                                }
                            ],
                        }
                    ]
                },
            }
        },
    }
    (tmp_path / "mail.yaml").write_text(yaml.safe_dump(source))
    (tmp_path / "root.yaml").write_text("name: root\nimports:\n  - path: mail.yaml\n    namespace: shared\n")
    scenario = parse_sdl_file(tmp_path / "root.yaml")
    mailbox = "nodes.shared.mail.runtime.mail_services.mail.mailboxes.admin"
    sink = InProcessMailboxSink(frozenset({("provision.account.shared.admin", mailbox)}))
    manager = RuntimeManager(create_reference_backend_target(domain_profile_context=context, mailbox_sink=sink))
    result = manager.apply(manager.plan(scenario))
    assert result.success, result.diagnostics
    assert sink.authenticates(mailbox, FIXTURE_SENTINEL)
    assert not sink.authenticates(binding.value["mailbox_ref"], FIXTURE_SENTINEL)
    assert manager.destroy().success
    assert not sink.authenticates(mailbox, FIXTURE_SENTINEL)
