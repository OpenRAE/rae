"""Legacy probe implementation declarations run on VMs.

A condition is either command-based (command + interval) or source-based (a
library package). It may explicitly bind the proposition it realizes, but its
command/source fields never define that proposition's meaning.
"""

from pydantic import Field, model_validator

from ._base import SDLModel, parse_int_or_var
from ._source import Source


class Condition(SDLModel):
    """A probe implementation deployed to a compute node.

    Either ``command`` + ``interval`` or ``source`` must be set, not both.
    """

    name: str = ""
    proposition: str = ""
    command: str | None = None
    interval: int | str | None = None
    timeout: int | str | None = None
    retries: int | str | None = None
    start_period: int | str | None = None
    source: Source | None = None
    description: str = ""
    environment: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def parse_scalar_fields(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            for field_name, minimum in (
                ("interval", 1),
                ("timeout", 1),
                ("retries", 0),
                ("start_period", 0),
            ):
                if field_name in data:
                    data[field_name] = parse_int_or_var(
                        data[field_name],
                        minimum=minimum,
                        field_name=field_name,
                    )
        return data

    @model_validator(mode="after")
    def validate_command_xor_source(self) -> Condition:
        has_command = self.command is not None
        has_interval = self.interval is not None
        has_source = self.source is not None

        if has_command and has_source:
            raise ValueError("Condition cannot have both 'command' and 'source'")
        if has_command and not has_interval:
            raise ValueError("Condition with 'command' requires 'interval'")
        if has_interval and not has_command:
            raise ValueError("Condition with 'interval' requires 'command'")
        if not has_command and not has_source:
            raise ValueError("Condition must have either 'command' + 'interval' or 'source'")
        return self
