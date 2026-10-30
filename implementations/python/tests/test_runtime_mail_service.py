"""Runtime mail-service SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes._module_symbols import symbol_index
from raes.nodes import (
    Node,
    RuntimeConfiguration,
    RuntimeMailAuthMechanism,
    RuntimeMailCredentialClassification,
    RuntimeMailMailboxRole,
    RuntimeMailMailboxStatus,
    RuntimeMailProtocol,
    RuntimeMailQueueStability,
    RuntimeMailService,
    RuntimeMailSetting,
    RuntimeMailSettingProvenance,
    RuntimeMailTlsMode,
)
from raes.relationships import Relationship, RelationshipMailAccess
from raes.scenario import ModuleDescriptor, Scenario
from raes.validator import SemanticValidator


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
    except SDLValidationError as exc:
        return exc.errors
    else:
        return []


def _mail_service(**overrides) -> dict:
    service = {
        "mail_service_id": "techvault-mail",
        "service": "smtp",
        "engine": "docker-mailserver",
        "version": "latest",
        "components": [
            {"component_id": "postfix", "kind": "mta", "name": "Postfix"},
            {"component_id": "dovecot", "kind": "imap_server", "name": "Dovecot"},
        ],
        "listeners": [
            {
                "listener_id": "smtp-listener",
                "service": "smtp",
                "protocol": "smtp",
                "role": "inbound_mx",
                "component_ref": "postfix",
                "banner": "mail.techvault.local ESMTP",
                "advertised_identity": "mail.techvault.local",
                "capabilities": ["PIPELINING", "STARTTLS", "AUTH PLAIN LOGIN"],
                "auth_mechanisms": ["plain", "login"],
                "tls_mode": "starttls_available",
            },
            {
                "listener_id": "imaps-listener",
                "service": "imaps",
                "protocol": "imaps",
                "role": "mail_access",
                "component_ref": "dovecot",
                "capabilities": ["IMAP4rev1", "AUTH=PLAIN"],
                "auth_mechanisms": ["plain"],
                "tls_mode": "implicit_tls",
            },
        ],
        "domains": [{"domain_id": "techvault-domain", "name": "techvault.local", "role": "local_delivery"}],
        "mailbox_stores": [
            {"store_id": "vmail-store", "kind": "maildir", "path": "/var/mail/vhosts/techvault.local"},
        ],
        "mailboxes": [
            {
                "mailbox_id": "admin-mailbox",
                "address": "admin@techvault.local",
                "domain_ref": "techvault-domain",
                "role": "admin",
                "status": "enabled",
                "auth_mechanisms": ["plain", "login"],
                "credential_classification": "fixture",
                "store_ref": "vmail-store",
            }
        ],
        "aliases": [
            {"alias_id": "postmaster-alias", "address": "postmaster@techvault.local", "target_refs": ["admin-mailbox"]},
        ],
        "routing_rules": [
            {
                "rule_id": "local-postmaster",
                "kind": "local_delivery",
                "source_ref": "postmaster-alias",
                "target_ref": "admin-mailbox",
            }
        ],
        "queues": [
            {"queue_id": "deferred-queue", "kind": "deferred", "name": "deferred", "message_count": 0},
        ],
        "settings": [
            {
                "setting_id": "postfix-hostname",
                "component_ref": "postfix",
                "name": "myhostname",
                "value": "mail.techvault.local",
                "provenance": "configuration_file",
                "source_path": "/etc/postfix/main.cf",
            }
        ],
    }
    service.update(overrides)
    return service


def _mail_node(service: dict | None = None) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "1 gib", "cpu": 1},
        "services": [
            {"port": 25, "name": "smtp"},
            {"port": 587, "name": "submission"},
            {"port": 143, "name": "imap"},
            {"port": 993, "name": "imaps"},
        ],
        "runtime": {
            "filesystem_inventory": [
                {"path": "/etc/postfix/main.cf", "entry_type": "file"},
                {"path": "/var/mail/vhosts/techvault.local", "entry_type": "directory"},
            ],
            "mail_services": [service or _mail_service()],
        },
    }


def test_mail_runtime_surface_is_node_scoped_not_top_level() -> None:
    assert "mail_services" not in Scenario.model_fields
    assert "mail" not in Scenario.model_fields
    assert "mail_services" in RuntimeConfiguration.model_fields


def test_vm_runtime_mail_service_surface() -> None:
    node = Node(type="compute", runtime={"mail_services": [_mail_service()]})

    service = node.runtime.mail_services[0]
    assert service.mail_service_id == "techvault-mail"
    assert service.listeners[0].protocol == RuntimeMailProtocol.SMTP
    assert service.listeners[0].auth_mechanisms == [
        RuntimeMailAuthMechanism.PLAIN,
        RuntimeMailAuthMechanism.LOGIN,
    ]
    assert service.listeners[1].tls_mode == RuntimeMailTlsMode.IMPLICIT_TLS
    assert service.mailboxes[0].role == RuntimeMailMailboxRole.ADMIN
    assert service.mailboxes[0].status == RuntimeMailMailboxStatus.ENABLED
    assert service.mailboxes[0].credential_classification == RuntimeMailCredentialClassification.FIXTURE
    assert service.queues[0].stability == RuntimeMailQueueStability.DYNAMIC
    assert service.settings[0].provenance == RuntimeMailSettingProvenance.CONFIGURATION_FILE


def test_parser_accepts_canonical_runtime_mail_services() -> None:
    scenario = parse_sdl(
        """
        name: mail-parser
        nodes:
          mail:
            type: compute
            resources: {ram: 1 gib, cpu: 1}
            services:
              - {port: 25, name: smtp}
            runtime:
              mail_services:
                - mail_service_id: techvault-mail
                  service: smtp
                  listeners:
                    - listener_id: smtp-listener
                      service: smtp
                      protocol: smtp
                      tls_mode: starttls-available
                  domains:
                    - domain_id: techvault-domain
                      name: techvault.local
                  mailboxes:
                    - mailbox_id: admin-mailbox
                      address: admin@techvault.local
                      domain_ref: techvault-domain
        """
    )

    service = scenario.nodes["mail"].runtime.mail_services[0]
    assert service.listeners[0].tls_mode == RuntimeMailTlsMode.STARTTLS_AVAILABLE
    assert service.mailboxes[0].domain_ref == "techvault-domain"


def test_runtime_mail_service_rejects_duplicate_stable_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime mail-service listener_id 'smtp-listener'"):
        RuntimeMailService(
            **_mail_service(
                listeners=[
                    {"listener_id": "smtp-listener", "service": "smtp", "protocol": "smtp"},
                    {"listener_id": "smtp-listener", "service": "submission", "protocol": "submission"},
                ]
            )
        )


def test_runtime_mail_setting_accepts_secret_named_scenario_value() -> None:
    setting = RuntimeMailSetting(
        setting_id="relay-auth",
        component_ref="postfix",
        name="smtp_sasl_password_maps",
        value="user:plaintext",
    )

    assert setting.value == "user:plaintext"


def test_runtime_mail_setting_rejects_redacted_raw_value() -> None:
    with pytest.raises(ValidationError, match="must omit its raw value"):
        RuntimeMailSetting(
            setting_id="relay-auth",
            component_ref="postfix",
            name="relay_password",
            value="secret",
            value_classification="redacted",
        )


class TestRuntimeMailSemanticValidation:
    def test_mail_service_validates_same_node_transport_refs_and_local_refs(self) -> None:
        assert _validate(Scenario(name="mail", nodes={"mail": _mail_node()})) == []

    def test_listener_service_ref_must_reference_same_node_service(self) -> None:
        service = _mail_service(
            listeners=[
                {
                    "listener_id": "smtp-listener",
                    "service": "nodes.other.services.smtp",
                    "protocol": "smtp",
                    "component_ref": "postfix",
                }
            ]
        )
        scenario = Scenario(
            name="mail",
            nodes={
                "mail": _mail_node(service),
                "other": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 25, "name": "smtp"}],
                },
            },
        )

        errors = _validate(scenario)
        assert any("listener 'smtp-listener'" in error and "same node" in error for error in errors)

    def test_mailbox_domain_ref_must_resolve_inside_service(self) -> None:
        service = _mail_service(
            mailboxes=[
                {
                    "mailbox_id": "admin-mailbox",
                    "address": "admin@techvault.local",
                    "domain_ref": "missing-domain",
                    "store_ref": "vmail-store",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("domain_ref 'missing-domain'" in error and "mail service" in error for error in errors)

    def test_listener_component_ref_must_resolve_inside_service(self) -> None:
        service = _mail_service(
            listeners=[
                {
                    "listener_id": "smtp-listener",
                    "service": "smtp",
                    "protocol": "smtp",
                    "component_ref": "missing-component",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("component_ref 'missing-component'" in error and "mail service" in error for error in errors)

    def test_mailbox_store_ref_must_resolve_inside_service(self) -> None:
        service = _mail_service(
            mailboxes=[
                {
                    "mailbox_id": "admin-mailbox",
                    "address": "admin@techvault.local",
                    "domain_ref": "techvault-domain",
                    "store_ref": "missing-store",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("store_ref 'missing-store'" in error and "mail service" in error for error in errors)

    def test_mailbox_account_ref_must_resolve_to_top_level_account(self) -> None:
        service = _mail_service(
            mailboxes=[
                {
                    "mailbox_id": "admin-mailbox",
                    "address": "admin@techvault.local",
                    "domain_ref": "techvault-domain",
                    "store_ref": "vmail-store",
                    "account_ref": "missing-account",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("account_ref 'missing-account'" in error for error in errors)

    def test_mailbox_local_user_ref_must_resolve_when_local_identity_is_present(self) -> None:
        service = _mail_service(
            mailboxes=[
                {
                    "mailbox_id": "admin-mailbox",
                    "address": "admin@techvault.local",
                    "domain_ref": "techvault-domain",
                    "store_ref": "vmail-store",
                    "local_user_ref": "missing-user",
                }
            ]
        )
        node = _mail_node(service)
        node["runtime"]["local_identity"] = {"users": [{"username": "real-user", "uid": 1000}]}
        errors = _validate(Scenario(name="mail", nodes={"mail": node}))
        assert any("local_user_ref 'missing-user'" in error for error in errors)

    def test_alias_target_ref_must_resolve_inside_service(self) -> None:
        service = _mail_service(aliases=[{"alias_id": "postmaster-alias", "target_refs": ["ghost-mailbox"]}])
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("target_ref 'ghost-mailbox'" in error and "mail service" in error for error in errors)

    def test_alias_domain_ref_must_resolve_inside_service(self) -> None:
        service = _mail_service(
            aliases=[
                {
                    "alias_id": "postmaster-alias",
                    "address": "postmaster@techvault.local",
                    "domain_ref": "missing-domain",
                    "target_refs": ["admin-mailbox"],
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("domain_ref 'missing-domain'" in error and "mail service" in error for error in errors)

    def test_routing_rule_refs_must_resolve_inside_service(self) -> None:
        service = _mail_service(
            routing_rules=[
                {
                    "rule_id": "bad-route",
                    "kind": "local_delivery",
                    "source_ref": "missing-source",
                    "target_ref": "missing-target",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("source_ref 'missing-source'" in error and "mail service" in error for error in errors)
        assert any("target_ref 'missing-target'" in error and "mail service" in error for error in errors)

    def test_setting_component_ref_must_resolve_inside_service(self) -> None:
        service = _mail_service(
            settings=[
                {
                    "setting_id": "postfix-hostname",
                    "component_ref": "missing-component",
                    "name": "myhostname",
                    "value": "mail.techvault.local",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("component_ref 'missing-component'" in error and "mail service" in error for error in errors)

    def test_setting_source_path_resolves_to_filesystem_inventory_when_present(self) -> None:
        service = _mail_service(
            settings=[
                {
                    "setting_id": "postfix-hostname",
                    "component_ref": "postfix",
                    "name": "myhostname",
                    "value": "mail.techvault.local",
                    "source_path": "/etc/postfix/missing.cf",
                }
            ]
        )
        errors = _validate(Scenario(name="mail", nodes={"mail": _mail_node(service)}))
        assert any("source_path '/etc/postfix/missing.cf'" in error for error in errors)


class TestRelationshipMailAccess:
    def _scenario(self, **relationship_overrides) -> Scenario:
        relationship = {
            "type": "connects_to",
            "source": "nodes.client",
            "target": "nodes.mail.runtime.mail_services.techvault-mail",
            "mail_access": {
                "protocol": "submission",
                "auth_mechanism": "plain",
                "tls_mode": "starttls_required",
                "mailbox_ref": "admin-mailbox",
                "domain_ref": "techvault-domain",
            },
        }
        relationship.update(relationship_overrides)
        return Scenario(
            name="mail",
            nodes={
                "mail": _mail_node(),
                "client": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            relationships={"client-to-mail": relationship},
        )

    def test_relationship_mail_access_block_is_typed(self) -> None:
        access = RelationshipMailAccess(protocol="SMTP", auth_mechanism="LOGIN", tls_mode="implicit_tls")
        assert access.protocol == RuntimeMailProtocol.SMTP
        assert access.auth_mechanism == RuntimeMailAuthMechanism.LOGIN
        relationship = Relationship(
            type="connects_to",
            source="nodes.client",
            target="nodes.mail.runtime.mail_services.techvault-mail",
            mail_access={"protocol": "imaps"},
        )
        assert relationship.mail_access.protocol == RuntimeMailProtocol.IMAPS

    def test_relationship_to_mail_service_is_valid(self) -> None:
        assert _validate(self._scenario()) == []

    def test_relationship_to_mail_listener_is_valid(self) -> None:
        scenario = self._scenario(target="nodes.mail.runtime.mail_services.techvault-mail.listeners.smtp-listener")
        assert _validate(scenario) == []

    def test_relationship_mail_access_target_must_resolve_to_mail_service(self) -> None:
        errors = _validate(self._scenario(target="nodes.mail.services.smtp"))
        assert any("does not resolve to a mail service" in error for error in errors)

    def test_relationship_mail_access_mailbox_ref_must_resolve(self) -> None:
        errors = _validate(self._scenario(mail_access={"mailbox_ref": "ghost-mailbox", "protocol": "smtp"}))
        assert any("mailbox_ref 'ghost-mailbox'" in error for error in errors)


def test_module_symbol_index_rewrites_runtime_mail_refs() -> None:
    scenario = Scenario(
        name="shared",
        module=ModuleDescriptor(id="acme/shared", version="1.0.0", exports={"nodes": ["mail"]}),
        nodes={"mail": _mail_node()},
    )

    named = symbol_index(
        scenario,
        namespace="shared",
        descriptor=scenario.module,
    )["named"]

    assert named["nodes.mail.runtime.mail_services.techvault-mail"] == (
        "nodes.shared.mail.runtime.mail_services.techvault-mail"
    )
    assert named["nodes.mail.runtime.mail_services.techvault-mail.listeners.smtp-listener"] == (
        "nodes.shared.mail.runtime.mail_services.techvault-mail.listeners.smtp-listener"
    )
    assert named["nodes.mail.runtime.mail_services.techvault-mail.mailboxes.admin-mailbox"] == (
        "nodes.shared.mail.runtime.mail_services.techvault-mail.mailboxes.admin-mailbox"
    )
