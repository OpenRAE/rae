"""Public account/mailbox semantics and the existing account credential join."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field

from ._base import ContractModel, NonEmptyString
from .canonical import canonical_json_digest
from .domain_profiles import DomainProfileSemanticContractModel
from .planning import ChangeAction, ProvisioningPlan, planned_node_spec, planned_resource_authored_name

ACCOUNT_MAILBOX_SEMANTICS = DomainProfileSemanticContractModel(
    authority="https://openrae.org/profiles",
    contract_id="account-mailbox-materialization",
    revision="1",
    digest=canonical_json_digest(
        {
            "contract": "account-mailbox-materialization/v1",
            "effect": "materialize the referenced mailbox using its owning account primary fixture credential",
            "authority": "exact account/mailbox join and independently authorized protected sink",
            "material": "primary password fixture; additional operator credentials remain references only",
        }
    ),
)


class AccountMailboxSelection(ContractModel):
    """Public selection data; material remains exclusively on Account."""

    mailbox_ref: NonEmptyString


@dataclass(frozen=True)
class AccountMailboxMaterialization:
    """Ephemeral protected-sink input, never a portable result or plan carrier."""

    account_address: str
    mailbox_ref: str
    fixture: str = field(repr=False)
    operator_references: tuple[str, ...] = field(repr=False)
    mailbox: Mapping[str, object] = field(repr=False)


def _resource_mailboxes(
    resource: object, selected_refs: set[str]
) -> Iterator[tuple[str, Mapping[str, object], Mapping[str, object]]]:
    node = planned_node_spec(resource)
    runtime = node.get("runtime") if node else None
    if not isinstance(runtime, Mapping):
        return
    name = planned_resource_authored_name(resource)
    for service in runtime.get("mail_services", ()):
        for mailbox in service.get("mailboxes", ()):
            reference = (
                f"nodes.{name}.runtime.mail_services.{service['mail_service_id']}.mailboxes.{mailbox['mailbox_id']}"
            )
            if reference in selected_refs:
                yield reference, service, mailbox


def _require_mailbox_posture(service: Mapping[str, object], mailbox: Mapping[str, object]) -> None:
    if any(value for key, value in service.items() if key not in {"mail_service_id", "mailboxes", "description"}):
        raise ValueError("Selected mailbox semantics do not implement general mail-service configuration")
    if (
        mailbox.get("status") not in (None, "unknown", "enabled")
        or mailbox.get("role") not in (None, "user")
        or mailbox.get("auth_mechanisms") not in (None, [], ["password"])
        or mailbox.get("credential_classification") not in (None, "unknown", "fixture")
        or any(mailbox.get(key) for key in ("domain_ref", "store_ref", "local_user_ref"))
    ):
        raise ValueError("Selected mailbox semantics do not implement the requested mailbox posture")


def _mailbox_inventory(plan: ProvisioningPlan, selected_refs: set[str]) -> dict[str, tuple[str, Mapping[str, object]]]:
    inventory = {}
    if not selected_refs:
        return inventory
    for resource in plan.resources.values():
        for reference, service, mailbox in _resource_mailboxes(resource, selected_refs):
            _require_mailbox_posture(service, mailbox)
            if reference in inventory:
                raise ValueError("Ambiguous mailbox materialization inventory")
            inventory[reference] = (resource.address, mailbox)
    return inventory


def _primary_material(spec: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    primary = []
    references = []
    for credential in spec.get("credential_bindings", ()):
        material = credential["material"]
        if credential["purpose"] == "primary_authentication":
            if credential["auth_method"] != "password" or material["classification"] != "secret_fixture":
                raise ValueError("Unsupported primary mailbox credential semantics")
            primary.append(material["value"])
        elif material["classification"] == "operator_secret":
            references.append(material["reference_id"])
        else:
            raise ValueError("Unsupported additional mailbox credential semantics")
    if len(primary) != 1 or not isinstance(primary[0], str) or spec.get("disabled") not in (None, False):
        raise ValueError("Mailbox materialization requires one enabled fixture-backed account")
    if spec.get("auth_method") != "password":
        raise ValueError("Mailbox authentication posture contradicts primary material")
    return primary[0], tuple(references)


def _account_bindings(operation: object) -> tuple[object, ...]:
    selected = tuple(
        binding for binding in operation.profile_bindings if binding.owner.context == "account-materialization"
    )
    if operation.payload.get("spec", {}).get("credential_bindings") and len(selected) != 1:
        raise ValueError("Credential-bearing accounts require exactly one supported materialization owner")
    return selected


def _mailbox_request(
    operation: object, binding: object, inventory: Mapping[str, tuple[str, Mapping[str, object]]]
) -> AccountMailboxMaterialization:
    selection = AccountMailboxSelection.model_validate(binding.value)
    row = inventory.get(selection.mailbox_ref)
    name = operation.payload.get("account_name")
    if row is None or row[0] != operation.payload.get("target_address"):
        raise ValueError("Mailbox and account must target the same node")
    mailbox = row[1]
    if mailbox.get("account_ref", "").removeprefix("accounts.") != name:
        raise ValueError("Mailbox must reference the exact owning account")
    fixture, references = _primary_material(operation.payload["spec"])
    return AccountMailboxMaterialization(
        operation.address, selection.mailbox_ref, fixture, references, deepcopy(mailbox)
    )


def _account_operations(plan: ProvisioningPlan) -> tuple[object, ...]:
    return tuple(
        operation
        for operation in plan.operations
        if operation.resource_type == "account-placement" and operation.action is not ChangeAction.DELETE
    )


def account_mailbox_materializations(plan: ProvisioningPlan) -> tuple[AccountMailboxMaterialization, ...]:
    """Join exact selected intent to inventory and its sole material owner."""

    operations = _account_operations(plan)
    selected_refs = {
        AccountMailboxSelection.model_validate(binding.value).mailbox_ref
        for operation in operations
        for binding in operation.profile_bindings
        if binding.owner.context == "account-materialization"
    }
    inventory = _mailbox_inventory(plan, selected_refs)
    requests = [
        _mailbox_request(operation, binding, inventory)
        for operation in operations
        for binding in _account_bindings(operation)
    ]
    if inventory.keys() != selected_refs:
        raise ValueError("Every selected mailbox requires matching materialization inventory")
    if len(requests) != len({request.mailbox_ref for request in requests}):
        raise ValueError("Mailbox materialization must have one unambiguous owner")
    return tuple(requests)
