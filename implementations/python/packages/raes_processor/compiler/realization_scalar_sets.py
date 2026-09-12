"""Finite collection choices use the shared relation's explicit identity aliases."""

from itertools import product

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.realization_structure import RealizationIdentityAlias


def bind_scalar_set_choices(document):
    """Preserve selected values beside alias identities; refuse ambiguous bounds."""

    remaining = [4096]

    def visit(rule):
        if rule.kind == "recursive-record":
            return rule.model_copy(update={"fields": {key: visit(value) for key, value in rule.fields.items()}})
        if rule.kind == "sequence":
            return rule.model_copy(update={"items": tuple(visit(item) for item in rule.items)})
        if rule.kind != "keyed-collection":
            return rule
        members = tuple(member.model_copy(update={"constraint": visit(member.constraint)}) for member in rule.members)
        aliases = []
        identities = {_identity_key(member.identity): member.identity for member in members}
        for member in members:
            child = member.constraint
            if child.kind != "recursive-record":
                continue
            if not any(
                field in child.fields and child.fields[field].kind == "domain" for field in rule.identity_fields
            ):
                continue
            choices = []
            for field, original in zip(rule.identity_fields, member.identity, strict=True):
                value = child.fields.get(field)
                if value is None or value.kind != "domain":
                    choices.append((original,))
                elif value.domain.kind == "enum":
                    choices.append(value.domain.values)
                else:
                    raise ValueError("collection identity domains require finite choices")
            for identity in product(*choices):
                remaining[0] -= 1
                if remaining[0] < 0 or any(type(candidate) not in {str, int, bool} for candidate in identity):
                    raise ValueError("collection choices exceed bounded identity authority")
                key = _identity_key(identity)
                if key in identities:
                    if _identity_key(identities[key]) != _identity_key(member.identity):
                        raise ValueError("collection domains have ambiguous member identities")
                    continue
                identities[key] = member.identity
                aliases.append(RealizationIdentityAlias(identity=identity, target=member.identity))
        return rule.model_copy(update={"members": members, "aliases": tuple(aliases)})

    return document.model_copy(update={"root": visit(document.root)})


def _identity_key(identity):
    return canonical_json_digest(list(identity))
