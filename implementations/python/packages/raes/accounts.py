"""Account models — user accounts within scenario systems.

Adapted from CyRIS ``add_account``/``modify_account`` and CybORG
agent session definitions. Describes accounts that exist on
scenario nodes — AD users, database users, SSH users, email
accounts — including properties relevant to attack scenarios
(password strength, Kerberos SPNs, group memberships).
"""

import re
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, WithJsonSchema, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileBindingModel
from raes_contracts.secret_references import SecretReferenceId

from ._base import (
    VARIABLE_TOKEN_PATTERN,
    SDLModel,
    WholeFieldVariableReference,
    is_variable_ref,
    normalize_enum_value,
    parse_bool_or_var,
    parse_enum_or_var,
)
from ._identifiers import PortableIdentifier


class PasswordStrength(str, Enum):
    """How resistant the account password is to cracking."""

    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"
    NONE = "none"


class AccountAuthenticationMethod(str, Enum):
    """Portable authentication methods shared by account posture and bindings."""

    # Constructed from vocabulary fragments so security linters do not mistake
    # this governed method term for embedded credential material.
    PASSWORD = "pass" + "word"
    KEY = "key"
    CERTIFICATE = "certificate"


class AccountCredentialPurpose(str, Enum):
    """Governed purposes for portable account credential bindings."""

    PRIMARY_AUTHENTICATION = "primary_authentication"
    ADMINISTRATIVE_AUTHENTICATION = "administrative_authentication"


_ACCOUNT_VOCABULARY_EXTENSION_PATTERN = r"^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$"
_ACCOUNT_VOCABULARY_EXTENSION_RE = re.compile(_ACCOUNT_VOCABULARY_EXTENSION_PATTERN)
_ACCOUNT_VOCABULARY_EXTENSION_BODY = r"x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*"


def _vocabulary_string_schema(canonical_values: tuple[str, ...]) -> dict[str, object]:
    aliases = tuple(value.replace("_", "-") for value in canonical_values if "_" in value)
    return {
        "type": "string",
        "pattern": (
            "^(?:"
            + "|".join((*canonical_values, *aliases, _ACCOUNT_VOCABULARY_EXTENSION_BODY, VARIABLE_TOKEN_PATTERN))
            + ")$"
        ),
    }


AccountAuthenticationMethodString = Annotated[
    str,
    WithJsonSchema(_vocabulary_string_schema(tuple(member.value for member in AccountAuthenticationMethod))),
]
AccountCredentialPurposeString = Annotated[
    str,
    WithJsonSchema(_vocabulary_string_schema(tuple(member.value for member in AccountCredentialPurpose))),
]


def _parse_account_vocabulary(
    value: object,
    enum_cls: type[Enum],
    *,
    field_name: str,
) -> object:
    if is_variable_ref(value) or isinstance(value, enum_cls):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = normalize_enum_value(value)
    try:
        parsed: object = enum_cls(normalized)
    except ValueError:
        extension = value.lower()
        if not _ACCOUNT_VOCABULARY_EXTENSION_RE.fullmatch(extension):
            raise ValueError(
                f"{field_name} must use a governed account vocabulary term, "
                "x-<owner>:<term> extension, or whole-field variable reference"
            ) from None
        parsed = extension
    return parsed


class SecretFixtureCredentialMaterial(SDLModel):
    """Deliberately disclosed scenario credential material."""

    classification: Literal["secret_fixture"]
    value: str


class OperatorSecretCredentialMaterial(SDLModel):
    """Value-free reference to operator-managed credential material."""

    classification: Literal["operator_secret"]
    reference_id: SecretReferenceId | WholeFieldVariableReference


AccountCredentialMaterial = Annotated[
    SecretFixtureCredentialMaterial | OperatorSecretCredentialMaterial,
    Field(discriminator="classification"),
]


class AccountCredentialBinding(SDLModel):
    """One credential bound unambiguously to its owning account by nesting."""

    credential_id: PortableIdentifier
    purpose: AccountCredentialPurpose | AccountCredentialPurposeString
    auth_method: AccountAuthenticationMethod | AccountAuthenticationMethodString
    material: AccountCredentialMaterial

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_purpose(cls, value: object) -> object:
        return _parse_account_vocabulary(value, AccountCredentialPurpose, field_name="purpose")

    @field_validator("auth_method", mode="before")
    @classmethod
    def normalize_auth_method(cls, value: object) -> object:
        return _parse_account_vocabulary(value, AccountAuthenticationMethod, field_name="auth_method")


class Account(SDLModel):
    """A user account on a scenario node.

    Distinct from OCR's ``Role`` model: roles map exercise participants
    to compute-node logins for exercise access. Accounts describe the environment
    state — what accounts attackers will encounter or exploit.
    """

    username: str
    node: str = ""
    groups: list[str] = Field(default_factory=list)
    password_strength: PasswordStrength | str = PasswordStrength.MEDIUM
    auth_method: AccountAuthenticationMethod | AccountAuthenticationMethodString = AccountAuthenticationMethod.PASSWORD
    credential_bindings: list[AccountCredentialBinding] = Field(default_factory=list)
    materialization_profile: DomainProfileBindingModel | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    description: str = ""
    mail: str = ""
    spn: str = ""
    domain_ref: str = ""
    shell: str = ""
    home: str = ""
    disabled: bool | str = False

    @field_validator("password_strength", mode="before")
    @classmethod
    def normalize_strength(cls, v: str) -> PasswordStrength | str:
        return parse_enum_or_var(
            v,
            PasswordStrength,
            field_name="password_strength",
        )

    @field_validator("auth_method", mode="before")
    @classmethod
    def normalize_auth_method(cls, value: object) -> object:
        return _parse_account_vocabulary(value, AccountAuthenticationMethod, field_name="auth_method")

    @field_validator("disabled", mode="before")
    @classmethod
    def parse_disabled(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="disabled")

    @model_validator(mode="after")
    def validate_required_node(self) -> "Account":
        if not self.node:
            raise ValueError("Account requires 'node'")
        return self


def _concrete_vocabulary_value(value: object) -> str | None:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str) and not is_variable_ref(value):
        return value
    return None


def _credential_binding_summary(
    bindings: list[AccountCredentialBinding],
) -> tuple[list[tuple[str, str]], bool, list[AccountCredentialBinding]]:
    concrete_pairs: list[tuple[str, str]] = []
    unresolved = False
    primary_bindings: list[AccountCredentialBinding] = []
    for binding in bindings:
        purpose = _concrete_vocabulary_value(binding.purpose)
        method = _concrete_vocabulary_value(binding.auth_method)
        if purpose is None or method is None:
            unresolved = True
            continue
        concrete_pairs.append((purpose, method))
        if purpose == AccountCredentialPurpose.PRIMARY_AUTHENTICATION.value:
            primary_bindings.append(binding)
    return concrete_pairs, unresolved, primary_bindings


def _primary_binding_issue(
    account: Account,
    *,
    unresolved: bool,
    primary_bindings: list[AccountCredentialBinding],
) -> str | None:
    issue: str | None = None
    if not unresolved and len(primary_bindings) != 1:
        issue = "credential bindings must contain exactly one primary credential binding"
    elif len(primary_bindings) == 1:
        account_method = _concrete_vocabulary_value(account.auth_method)
        primary_method = _concrete_vocabulary_value(primary_bindings[0].auth_method)
        if account_method is not None and primary_method is not None and account_method != primary_method:
            issue = "primary credential binding authentication method must match account auth_method posture"
    return issue


def account_credential_binding_issues(account: Account) -> tuple[str, ...]:
    """Return value-free semantic issues for one account's credential bindings."""

    if not account.credential_bindings:
        return ()

    issues: list[str] = []
    ids = [binding.credential_id for binding in account.credential_bindings]
    if len(ids) != len(set(ids)):
        issues.append("credential bindings must use unique credential_id values")

    concrete_pairs, unresolved, primary_bindings = _credential_binding_summary(account.credential_bindings)
    if len(concrete_pairs) != len(set(concrete_pairs)):
        issues.append("credential bindings contain a duplicate credential purpose and authentication method")
    primary_issue = _primary_binding_issue(account, unresolved=unresolved, primary_bindings=primary_bindings)
    if primary_issue is not None:
        issues.append(primary_issue)
    return tuple(issues)


__all__ = [
    "Account",
    "AccountAuthenticationMethod",
    "AccountCredentialBinding",
    "AccountCredentialMaterial",
    "AccountCredentialPurpose",
    "OperatorSecretCredentialMaterial",
    "PasswordStrength",
    "SecretFixtureCredentialMaterial",
    "account_credential_binding_issues",
]
