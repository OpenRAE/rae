"""Source adapters for existing typed profile bindings and precise built-ins."""

from enum import Enum

from raes_contracts.domain_profiles import DomainProfileBindingModel

from .value_parsing import parse_enum_or_var


def parse_profile_or_enum(value: object, enum_cls: type[Enum], *, field_name: str) -> object:
    """Retain the shared binding shape without interpreting or loading its meaning."""

    if isinstance(value, (dict, DomainProfileBindingModel)):
        return DomainProfileBindingModel.model_validate(value)
    return parse_enum_or_var(value, enum_cls, field_name=field_name)


def profile_owned_mailbox_inventory(scenario: object, node_name: str) -> bool:
    """Recognize mailbox-only inventory whose materialization has an explicit owner.

    The exact inventory remains a core constraint. Its selected typed contract
    owns operational verification; unrelated mail-server configuration keeps
    the incumbent guest-readback contract.
    """

    runtime = scenario.nodes[node_name].runtime
    if runtime is None or not runtime.mail_services:
        return False
    for service in runtime.mail_services:
        other = service.model_dump(exclude={"mail_service_id", "mailboxes", "description"})
        if any(other.values()) or not service.mailboxes:
            return False
        for mailbox in service.mailboxes:
            account = scenario.accounts.get(mailbox.account_ref.removeprefix("accounts."))
            binding = getattr(account, "materialization_profile", None)
            reference = (
                f"nodes.{node_name}.runtime.mail_services.{service.mail_service_id}.mailboxes.{mailbox.mailbox_id}"
            )
            if (
                not isinstance(binding, DomainProfileBindingModel)
                or binding.owner.context != "account-materialization"
                or not isinstance(binding.value, dict)
                or binding.value.get("mailbox_ref") != reference
            ):
                return False
    return True
