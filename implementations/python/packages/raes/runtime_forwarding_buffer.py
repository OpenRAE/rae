"""Typed forwarding buffer policy, re-exported by the family facade."""

from pydantic import ValidationInfo, field_validator

from ._base import SDLModel, parse_int_or_var
from .runtime_forwarding_agent_vocab import RuntimeForwardingBufferCrypto
from .runtime_values import parse_runtime_enum_or_var, require_symbol
from .runtime_vocabulary import GovernedVocabulary


class RuntimeForwardingBufferPolicy(SDLModel):
    """The single observed buffer / back-pressure posture of a forwarder.

    Captures the ``client_buffer`` shape: queue capacity, events-per-second
    ceiling, at-rest/in-transit crypto, and reconnect interval. Its presence is
    the defining profile a ``log_forwarder`` must carry.
    """

    buffer_policy_id: str
    queue_capacity: int | str | None = None
    eps: int | str | None = None
    crypto: GovernedVocabulary[RuntimeForwardingBufferCrypto] = RuntimeForwardingBufferCrypto.UNKNOWN
    reconnect_seconds: int | str | None = None
    description: str = ""

    @field_validator("buffer_policy_id")
    @classmethod
    def validate_buffer_policy_id(cls, v: str) -> str:
        return require_symbol(v, field_name="buffer_policy_id")

    @field_validator("queue_capacity", "eps", "reconnect_seconds", mode="before")
    @classmethod
    def parse_counts(cls, v: object, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v

    @field_validator("crypto", mode="before")
    @classmethod
    def normalize_crypto(cls, v: RuntimeForwardingBufferCrypto | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingBufferCrypto, field_name="crypto")
