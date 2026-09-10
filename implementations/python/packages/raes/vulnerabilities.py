"""Historical vulnerability syntax for explicit classification migration only.

Each vulnerability is classified by its CWE identifier (e.g., CWE-89
for SQL injection). This compatibility reader is not a canonical SDL section,
native predicate, compiler template, or evidence of realized weakness.
"""

import re

from pydantic import Field, field_validator

from ._base import SDLModel, parse_bool_or_var

_CWE_PATTERN = re.compile(r"^CWE-\d+$")


class Vulnerability(SDLModel):
    """A named vulnerability with CWE classification."""

    name: str
    description: str
    technical: bool | str = False
    vuln_class: str = Field(alias="class")

    @field_validator("technical", mode="before")
    @classmethod
    def parse_technical(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="technical")

    @field_validator("vuln_class")
    @classmethod
    def validate_cwe_format(cls, v: str) -> str:
        if not _CWE_PATTERN.match(v):
            raise ValueError(f"Vulnerability class must match CWE-NNN format, got: {v!r}")
        return v
