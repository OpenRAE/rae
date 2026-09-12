"""Service aggregate and relationship-access models for runtime mail.

:class:`RuntimeMailService` is the node-scoped aggregate over the element
records in :mod:`._elements`; :class:`RelationshipMailAccess` carries typed
mail-access detail on a top-level relationship edge.
"""

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from .._base import SDLModel
from ..runtime_mail_vocab import (
    RuntimeMailAuthMechanism,
    RuntimeMailProtocol,
    RuntimeMailTlsMode,
)
from ..runtime_values import (
    parse_runtime_enum_or_var,
    reject_duplicates,
    require_symbol,
)
from ._elements import (
    RuntimeMailAlias,
    RuntimeMailComponent,
    RuntimeMailDomain,
    RuntimeMailListener,
    RuntimeMailMailbox,
    RuntimeMailMailboxStore,
    RuntimeMailQueue,
    RuntimeMailRoutingRule,
    RuntimeMailSetting,
)

_DUPLICATE_MAIL_TEMPLATE = "Duplicate runtime mail-service {label} '{value}' in {container_label}"


class RuntimeMailService(SDLModel):
    """A node-scoped runtime mail-service logical inventory."""

    mail_service_id: str
    service: str = ""
    engine: str = ""
    version: str = ""
    name: str = ""
    description: str = ""
    components: list[RuntimeMailComponent] = Field(default_factory=list)
    listeners: list[RuntimeMailListener] = Field(default_factory=list)
    domains: list[RuntimeMailDomain] = Field(default_factory=list)
    mailbox_stores: list[RuntimeMailMailboxStore] = Field(default_factory=list)
    mailboxes: list[RuntimeMailMailbox] = Field(default_factory=list)
    aliases: list[RuntimeMailAlias] = Field(default_factory=list)
    routing_rules: list[RuntimeMailRoutingRule] = Field(default_factory=list)
    queues: list[RuntimeMailQueue] = Field(default_factory=list)
    settings: list[RuntimeMailSetting] = Field(default_factory=list)

    @field_validator("mail_service_id")
    @classmethod
    def validate_mail_service_id(cls, v: str) -> str:
        return require_symbol(v, field_name="mail_service_id")

    @model_validator(mode="after")
    def validate_service(self) -> "RuntimeMailService":
        self._reject_duplicate_collection_ids()
        self._reject_duplicate_local_ref_ids()
        return self

    def _reject_duplicate_collection_ids(self) -> None:
        for label, attr in (
            ("component_id", "components"),
            ("listener_id", "listeners"),
            ("domain_id", "domains"),
            ("store_id", "mailbox_stores"),
            ("mailbox_id", "mailboxes"),
            ("alias_id", "aliases"),
            ("rule_id", "routing_rules"),
            ("queue_id", "queues"),
            ("setting_id", "settings"),
        ):
            reject_duplicates(
                [getattr(item, label) for item in getattr(self, attr)],
                label=label,
                container_label=f"mail service '{self.mail_service_id}'",
                duplicate_template=_DUPLICATE_MAIL_TEMPLATE,
                skip_empty=False,
            )

    def _reject_duplicate_local_ref_ids(self) -> None:
        entries: list[tuple[str, str]] = [("mail_service_id", self.mail_service_id)]
        for label, collection_name in (
            ("component_id", "components"),
            ("listener_id", "listeners"),
            ("domain_id", "domains"),
            ("store_id", "mailbox_stores"),
            ("mailbox_id", "mailboxes"),
            ("alias_id", "aliases"),
            ("rule_id", "routing_rules"),
            ("queue_id", "queues"),
            ("setting_id", "settings"),
        ):
            entries.extend((label, getattr(item, label)) for item in getattr(self, collection_name))

        seen: dict[str, str] = {}
        for label, value in entries:
            prior = seen.get(value)
            if prior is not None:
                raise ValueError(
                    f"Duplicate runtime mail-service stable id '{value}' in service "
                    f"'{self.mail_service_id}' across {prior} and {label}"
                )
            seen[value] = label


class RelationshipMailAccess(SDLModel):
    """Typed mail-access detail carried by a top-level relationship edge."""

    protocol: GovernedVocabulary[RuntimeMailProtocol] = RuntimeMailProtocol.OTHER
    auth_mechanism: GovernedVocabulary[RuntimeMailAuthMechanism] = RuntimeMailAuthMechanism.OTHER
    tls_mode: GovernedVocabulary[RuntimeMailTlsMode] = RuntimeMailTlsMode.UNKNOWN
    listener_ref: str = ""
    mailbox_ref: str = ""
    domain_ref: str = ""
    description: str = ""

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: RuntimeMailProtocol | str) -> RuntimeMailProtocol | str:
        return parse_runtime_enum_or_var(v, RuntimeMailProtocol, field_name="protocol")

    @field_validator("auth_mechanism", mode="before")
    @classmethod
    def normalize_auth_mechanism(cls, v: RuntimeMailAuthMechanism | str) -> RuntimeMailAuthMechanism | str:
        return parse_runtime_enum_or_var(v, RuntimeMailAuthMechanism, field_name="auth_mechanism")

    @field_validator("tls_mode", mode="before")
    @classmethod
    def normalize_tls_mode(cls, v: RuntimeMailTlsMode | str) -> RuntimeMailTlsMode | str:
        return parse_runtime_enum_or_var(v, RuntimeMailTlsMode, field_name="tls_mode")
