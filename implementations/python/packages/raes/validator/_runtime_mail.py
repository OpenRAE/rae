"""SemanticValidator _RuntimeMailMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .._reference_targetability import ReferencePurpose
from ._core import runtime_reference_eligible


@dataclass(frozen=True)
class _MailServiceLocalIds:
    components: set[str]
    domains: set[str]
    stores: set[str]
    mailboxes: set[str]
    aliases: set[str]
    routing_refs: set[str]


_MailChildIdReader = Callable[[object], Iterable[str]]
_MAIL_CHILD_ID_READERS: dict[str, _MailChildIdReader] = {
    "components": lambda service: (component.component_id for component in service.components),
    "listeners": lambda service: (listener.listener_id for listener in service.listeners),
    "domains": lambda service: (domain.domain_id for domain in service.domains),
    "mailbox_stores": lambda service: (store.store_id for store in service.mailbox_stores),
    "mailboxes": lambda service: (mailbox.mailbox_id for mailbox in service.mailboxes),
    "aliases": lambda service: (alias.alias_id for alias in service.aliases),
    "routing_rules": lambda service: (rule.rule_id for rule in service.routing_rules),
    "queues": lambda service: (queue.queue_id for queue in service.queues),
    "settings": lambda service: (setting.setting_id for setting in service.settings),
}


def _mail_services_for_node(node: object) -> Sequence[object]:
    runtime = getattr(node, "runtime", None)
    return () if runtime is None else runtime.mail_services


def _collect_mail_service_local_ids(service: object) -> _MailServiceLocalIds:
    mailbox_ids = {mailbox.mailbox_id for mailbox in service.mailboxes}
    alias_ids = {alias.alias_id for alias in service.aliases}
    domain_ids = {domain.domain_id for domain in service.domains}
    return _MailServiceLocalIds(
        components={component.component_id for component in service.components},
        domains=domain_ids,
        stores={store.store_id for store in service.mailbox_stores},
        mailboxes=mailbox_ids,
        aliases=alias_ids,
        routing_refs=mailbox_ids | alias_ids | domain_ids,
    )


def _mail_child_ref_exists(service: object, collection_name: str, child_id: str) -> bool:
    read_child_ids = _MAIL_CHILD_ID_READERS.get(collection_name)
    return read_child_ids is not None and child_id in read_child_ids(service)


class _RuntimeMailMixin:
    def _verify_runtime_mail_services(self) -> None:
        """Validate runtime mail-service inventories against the scenario graph."""
        for node_name, node in self._s.nodes.items():
            mail_services = _mail_services_for_node(node)
            if not mail_services:
                continue
            service_names = self._node_service_names(node)
            observed_paths = self._node_observed_paths(node)
            local_user_names = self._node_local_user_names(node)
            for service in mail_services:
                label = f"Node '{node_name}' runtime mail service '{service.mail_service_id}'"
                with self._owner(("nodes", node_name)):
                    self._verify_owned_service_ref(
                        node_name,
                        service.service,
                        service_names,
                        owner_label=label,
                    )
                    self._verify_mail_service_children(
                        node_name=node_name,
                        label=label,
                        service=service,
                        service_names=service_names,
                        observed_paths=observed_paths,
                        local_user_names=local_user_names,
                    )

    def _verify_mail_service_children(
        self,
        *,
        node_name: str,
        label: str,
        service: object,
        service_names: set[str],
        observed_paths: set[str],
        local_user_names: set[str],
    ) -> None:
        local_ids = _collect_mail_service_local_ids(service)
        self._verify_mail_listeners(node_name, label, service, service_names, local_ids)
        self._verify_mailboxes(label, service, local_user_names, local_ids)
        self._verify_mail_aliases(label, service, local_ids)
        self._verify_mail_routing_rules(label, service, local_ids)
        self._verify_mail_settings(label, service, observed_paths, local_ids)

    def _verify_mail_listeners(
        self,
        node_name: str,
        label: str,
        service: object,
        service_names: set[str],
        local_ids: _MailServiceLocalIds,
    ) -> None:
        for listener in service.listeners:
            listener_label = f"{label} listener '{listener.listener_id}'"
            self._verify_owned_service_ref(
                node_name,
                listener.service,
                service_names,
                owner_label=listener_label,
            )
            self._verify_mail_ref(
                listener.component_ref,
                local_ids.components,
                label=listener_label,
                field_name="component_ref",
            )

    def _verify_mailboxes(
        self,
        label: str,
        service: object,
        local_user_names: set[str],
        local_ids: _MailServiceLocalIds,
    ) -> None:
        for mailbox in service.mailboxes:
            mailbox_label = f"{label} mailbox '{mailbox.mailbox_id}'"
            self._verify_mail_ref(mailbox.domain_ref, local_ids.domains, label=mailbox_label, field_name="domain_ref")
            self._verify_mail_ref(mailbox.store_ref, local_ids.stores, label=mailbox_label, field_name="store_ref")
            self._verify_mail_account_ref(mailbox.account_ref, mailbox_label)
            self._verify_mail_local_user_ref(mailbox.local_user_ref, local_user_names, mailbox_label)

    def _verify_mail_aliases(
        self,
        label: str,
        service: object,
        local_ids: _MailServiceLocalIds,
    ) -> None:
        for alias in service.aliases:
            alias_label = f"{label} alias '{alias.alias_id}'"
            self._verify_mail_ref(alias.domain_ref, local_ids.domains, label=alias_label, field_name="domain_ref")
            for target_ref in alias.target_refs:
                self._verify_mail_ref(
                    target_ref,
                    local_ids.mailboxes | local_ids.aliases,
                    label=alias_label,
                    field_name="target_ref",
                )

    def _verify_mail_routing_rules(
        self,
        label: str,
        service: object,
        local_ids: _MailServiceLocalIds,
    ) -> None:
        for rule in service.routing_rules:
            rule_label = f"{label} routing rule '{rule.rule_id}'"
            self._verify_mail_ref(rule.source_ref, local_ids.routing_refs, label=rule_label, field_name="source_ref")
            self._verify_mail_ref(rule.target_ref, local_ids.routing_refs, label=rule_label, field_name="target_ref")

    def _verify_mail_settings(
        self,
        label: str,
        service: object,
        observed_paths: set[str],
        local_ids: _MailServiceLocalIds,
    ) -> None:
        for setting in service.settings:
            setting_label = f"{label} setting '{setting.setting_id}'"
            self._verify_mail_ref(
                setting.component_ref,
                local_ids.components,
                label=setting_label,
                field_name="component_ref",
            )
            if self._source_path_misses_observed_inventory(setting.source_path, observed_paths):
                self._err(f"{setting_label} source_path '{setting.source_path}' does not resolve to an observed file")

    def _source_path_misses_observed_inventory(self, source_path: str, observed_paths: set[str]) -> bool:
        return bool(
            source_path
            and observed_paths
            and not self._is_unresolved_var(source_path)
            and source_path not in observed_paths
        )

    def _verify_mail_ref(
        self,
        ref: str,
        local_refs: set[str],
        *,
        label: str,
        field_name: str,
    ) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        if ref not in local_refs:
            self._err(f"{label} {field_name} '{ref}' does not resolve inside mail service")

    def _verify_mail_account_ref(self, ref: str, label: str) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        if ref not in self._s.accounts:
            self._err(f"{label} account_ref '{ref}' does not resolve to a top-level account")

    def _verify_mail_local_user_ref(self, ref: str, local_user_names: set[str], label: str) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        if local_user_names and ref not in local_user_names:
            self._err(f"{label} local_user_ref '{ref}' does not resolve to a runtime.local_identity user")

    def _verify_relationship_mail_access(self) -> None:
        """Validate typed ``mail_access`` blocks on top-level relationship edges."""
        for name, relationship in self._s.relationships.items():
            access = relationship.mail_access
            if access is None:
                continue
            label = f"Relationship '{name}'"
            with self._owner(("relationships", name)):
                mail_service = self._check_mail_access_target(relationship.target, label)
                if mail_service is None:
                    continue
                self._verify_mail_ref(
                    access.listener_ref,
                    {listener.listener_id for listener in mail_service.listeners},
                    label=f"{label} mail_access",
                    field_name="listener_ref",
                )
                self._verify_mail_ref(
                    access.mailbox_ref,
                    {mailbox.mailbox_id for mailbox in mail_service.mailboxes},
                    label=f"{label} mail_access",
                    field_name="mailbox_ref",
                )
                self._verify_mail_ref(
                    access.domain_ref,
                    {domain.domain_id for domain in mail_service.domains},
                    label=f"{label} mail_access",
                    field_name="domain_ref",
                )

    def _check_mail_access_target(self, target: str, label: str) -> object | None:
        mail_service = self._resolve_mail_service_ref(target)
        if mail_service is not None or self._is_unresolved_var(target):
            return mail_service
        self._err(f"{label} has mail_access but target '{target}' does not resolve to a mail service")
        return None

    def _resolve_mail_service_ref(self, ref: object) -> object | None:
        """Resolve a qualified runtime mail-service or child ref to the service."""
        reference = self._runtime_reference(ref)
        return (
            reference.owning_item
            if runtime_reference_eligible(reference, ReferencePurpose.MAIL_SERVICE_ENDPOINT)
            else None
        )
