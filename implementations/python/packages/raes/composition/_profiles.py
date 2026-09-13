"""Owner-aware composition for the existing typed selection hosts."""

from collections.abc import Mapping

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.profile_selections import profile_selection_binding

from ._references import _maybe_rename


def rewrite_profile_selections(payload: dict, symbols: dict) -> None:
    """Rewrite only declared binding hosts, never discover bindings in private data."""
    for section, field in (
        ("accounts", "materialization_profile"),
        ("generated_artifacts", "generator"),
        ("content", "service_materialization"),
        ("identity_domains", "profile"),
        ("identity_facades", "protocol"),
    ):
        for declaration in payload.get(section, {}).values():
            _rewrite_binding(declaration.get(field), symbols)
    for relationship in payload.get("relationships", {}).values():
        for detail, fields in (
            ("forest_trust", ("trust_type",)),
            ("identity_federation", ("protocol", "mapping_intent")),
        ):
            for field in fields:
                _rewrite_binding((relationship.get(detail) or {}).get(field), symbols)
    for agent in payload.get("agents", {}).values():
        for access in agent.get("interactive_access", {}).values():
            _rewrite_binding(access.get("channel"), symbols)


def _rewrite_binding(binding: object, symbols: dict) -> None:
    if not isinstance(binding, dict) or profile_selection_binding(binding) is None:
        return
    owner = binding["owner"]
    previous_owner = owner["canonical_address"]
    owner["canonical_address"] = _rewrite_owner(previous_owner, symbols)
    if owner["canonical_address"] != previous_owner:
        # Host-local ids must remain unique when a module is imported twice.
        # A bounded digest also handles legal SDL namespaces with underscores.
        binding["binding_id"] = "composed-" + canonical_json_digest(
            {"owner": owner["canonical_address"], "binding_id": binding["binding_id"]}
        ).removeprefix("sha256:")
    if owner["context"] == "account-materialization" and isinstance(binding.get("value"), dict):
        value = binding["value"]
        if isinstance(value.get("mailbox_ref"), str):
            value["mailbox_ref"] = _maybe_rename(value["mailbox_ref"], symbols["named"])
    for child in binding.get("children", ()):
        _rewrite_binding(child, symbols)


def _rewrite_owner(address: str, symbols: dict) -> str:
    if address.startswith("#/resources/"):
        compiled = address.removeprefix("#/resources/")
        for kind, section in (
            ("node", "nodes"),
            ("account", "accounts"),
            ("content", "content"),
            ("generated-artifact", "generated_artifacts"),
            ("persistent-volume", "persistent_volumes"),
        ):
            prefix = f"provision.{kind}."
            if compiled.startswith(prefix):
                return "#/resources/" + prefix + _maybe_rename(compiled.removeprefix(prefix), symbols[section])
        prefix = "provision.domain-controller."
        if compiled.startswith(prefix):
            suffix = compiled.removeprefix(prefix)
            matches = [
                (domain, suffix[len(domain) + 1 :])
                for domain in symbols["identity_domains"]
                if suffix.startswith(domain + ".") and suffix[len(domain) + 1 :] in symbols["nodes"]
            ]
            if len(matches) > 1:
                raise ValueError("Ambiguous composed profile owner")
            if matches:
                domain, node = matches[0]
                return "#/resources/" + prefix + symbols["identity_domains"][domain] + "." + symbols["nodes"][node]
        return address
    parts = address.split("/")
    if len(parts) >= 3:
        section = parts[1].replace("~1", "/").replace("~0", "~")
        names = symbols.get(section)
        if isinstance(names, Mapping):
            name = parts[2].replace("~1", "/").replace("~0", "~")
            parts[2] = _maybe_rename(name, names).replace("~", "~0").replace("/", "~1")
    return "/".join(parts)
