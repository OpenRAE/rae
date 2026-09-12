"""DNS RRset and common RDATA models for runtime inventory."""

import ipaddress

from pydantic import Field, ValidationInfo, field_validator, model_validator

from ._base import SDLModel, is_variable_ref, parse_int_or_var
from .runtime_dns_vocab import DnsRecordClass, DnsRecordProvenance, DnsRecordType
from .runtime_values import coerce_string_list, parse_runtime_enum_or_var, require_non_empty, require_symbol

__all__ = [
    "DnsMxRdata",
    "DnsResourceRecord",
    "DnsResourceRecordSet",
    "DnsSrvRdata",
    "DnsSoaRdata",
]

_MAX_UINT16 = 65_535
_MAX_UINT32 = 4_294_967_295
_MIN_PORT = 1
_MAX_PORT = 65_535
_ADDRESS_RECORD_TYPES = frozenset({DnsRecordType.A, DnsRecordType.AAAA})
_TARGET_RECORD_TYPES = frozenset({DnsRecordType.CNAME, DnsRecordType.NS, DnsRecordType.PTR})


def _dns_name_or_var(value: str, *, field_name: str) -> str:
    if is_variable_ref(value):
        return value
    require_non_empty(value, field_name=field_name)
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must not contain whitespace")
    return value


def _parse_uint16_or_var(value: object, *, field_name: str) -> int | str:
    return parse_int_or_var(value, minimum=0, maximum=_MAX_UINT16, field_name=field_name)


def _parse_uint32_or_var(value: object, *, field_name: str) -> int | str:
    return parse_int_or_var(value, minimum=0, maximum=_MAX_UINT32, field_name=field_name)


def _parse_port_or_var(value: object, *, field_name: str) -> int | str:
    return parse_int_or_var(value, minimum=_MIN_PORT, maximum=_MAX_PORT, field_name=field_name)


def _is_unresolved_variable(value: object) -> bool:
    return isinstance(value, str) and is_variable_ref(value)


class DnsSoaRdata(SDLModel):
    """Typed SOA RDATA fields."""

    mname: str
    rname: str
    serial: int | str
    refresh: int | str
    retry: int | str
    expire: int | str
    minimum: int | str

    @field_validator("mname", "rname")
    @classmethod
    def validate_names(cls, v: str, info: ValidationInfo) -> str:
        return _dns_name_or_var(v, field_name=info.field_name)

    @field_validator("serial", "refresh", "retry", "expire", "minimum", mode="before")
    @classmethod
    def parse_timers(cls, v: object, info: ValidationInfo) -> int | str:
        return _parse_uint32_or_var(v, field_name=info.field_name)


class DnsMxRdata(SDLModel):
    """Typed MX RDATA fields."""

    preference: int | str
    exchange: str

    @field_validator("preference", mode="before")
    @classmethod
    def parse_preference(cls, v: object) -> int | str:
        return _parse_uint16_or_var(v, field_name="MX preference")

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        return _dns_name_or_var(v, field_name="MX exchange")


class DnsSrvRdata(SDLModel):
    """Typed SRV RDATA fields."""

    priority: int | str
    weight: int | str
    port: int | str
    target: str

    @field_validator("priority", "weight", mode="before")
    @classmethod
    def parse_uint16(cls, v: object, info: ValidationInfo) -> int | str:
        return _parse_uint16_or_var(v, field_name=f"SRV {info.field_name}")

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, v: object) -> int | str:
        return _parse_port_or_var(v, field_name="SRV port")

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        return _dns_name_or_var(v, field_name="SRV target")


class DnsResourceRecord(SDLModel):
    """One observed record within an RRset."""

    rdata: str = ""
    address: str = ""
    target: str = ""
    text: list[str] = Field(default_factory=list)
    soa: DnsSoaRdata | None = None
    mx: DnsMxRdata | None = None
    srv: DnsSrvRdata | None = None
    description: str = ""

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        return _dns_name_or_var(v, field_name="record target") if v else v

    @field_validator("text", mode="before")
    @classmethod
    def coerce_text(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: list[str]) -> list[str]:
        for item in v:
            if not isinstance(item, str) or not item:
                raise ValueError("TXT record text entries must be non-empty strings")
        return v

    @model_validator(mode="after")
    def validate_payload_present(self) -> "DnsResourceRecord":
        if any((self.rdata, self.address, self.target, self.text, self.soa, self.mx, self.srv)):
            return self
        raise ValueError("DNS record must carry rdata or a typed payload")


class DnsResourceRecordSet(SDLModel):
    """Records grouped by owner name, class, type, and TTL."""

    rrset_id: str
    owner: str
    record_type: DnsRecordType | str
    zone_class: DnsRecordClass | str = DnsRecordClass.IN
    ttl: int | str | None = None
    type_code: int | str | None = None
    records: list[DnsResourceRecord] = Field(default_factory=list)
    provenance: DnsRecordProvenance | str = DnsRecordProvenance.UNKNOWN
    description: str = ""

    def explicitness_exact_fields(self) -> frozenset[str]:
        """The OTHER discriminator names an exact type when paired with its code."""

        return frozenset({"record_type"}) if type(self.type_code) is int else frozenset()

    @field_validator("rrset_id")
    @classmethod
    def validate_rrset_id(cls, v: str) -> str:
        return require_symbol(v, field_name="rrset_id")

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, v: str) -> str:
        return _dns_name_or_var(v, field_name="RRset owner")

    @field_validator("record_type", mode="before")
    @classmethod
    def normalize_record_type(cls, v: DnsRecordType | str) -> DnsRecordType | str:
        return parse_runtime_enum_or_var(v, DnsRecordType, field_name="record_type")

    @field_validator("zone_class", mode="before")
    @classmethod
    def normalize_zone_class(cls, v: DnsRecordClass | str) -> DnsRecordClass | str:
        return parse_runtime_enum_or_var(v, DnsRecordClass, field_name="zone_class")

    @field_validator("ttl", mode="before")
    @classmethod
    def parse_ttl(cls, v: object) -> int | str | None:
        return _parse_uint32_or_var(v, field_name="ttl") if v is not None else v

    @field_validator("type_code", mode="before")
    @classmethod
    def parse_type_code(cls, v: object) -> int | str | None:
        return _parse_uint16_or_var(v, field_name="type_code") if v is not None else v

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: DnsRecordProvenance | str) -> DnsRecordProvenance | str:
        return parse_runtime_enum_or_var(v, DnsRecordProvenance, field_name="provenance")

    @model_validator(mode="after")
    def validate_rrset(self) -> "DnsResourceRecordSet":
        if not self.records:
            raise ValueError("DNS RRset records must not be empty")
        record_type_is_variable = _is_unresolved_variable(self.record_type)
        if not record_type_is_variable and self.record_type == DnsRecordType.OTHER and self.type_code is None:
            raise ValueError("DNS RRset with record_type 'other' must set type_code")
        if not record_type_is_variable and self.record_type != DnsRecordType.OTHER and self.type_code is not None:
            raise ValueError("DNS RRset type_code is only valid when record_type is 'other'")
        for record in self.records:
            self._validate_record_payload(record)
        return self

    def _validate_record_payload(self, record: DnsResourceRecord) -> None:
        if _is_unresolved_variable(self.record_type):
            self._validate_variable_record_payload(record)
            return
        if record.address:
            self._validate_address(record.address)
        self._validate_target_payload(record)
        self._validate_common_typed_payloads(record)

    def _validate_variable_record_payload(self, record: DnsResourceRecord) -> None:
        if record.address and not _is_unresolved_variable(record.address):
            self._validate_ip_address(record.address, field_name="address")

    def _validate_target_payload(self, record: DnsResourceRecord) -> None:
        if record.target and self.record_type not in _TARGET_RECORD_TYPES:
            raise ValueError("target typed payload is only valid on CNAME, NS, or PTR RRsets")

    def _validate_common_typed_payloads(self, record: DnsResourceRecord) -> None:
        payload_checks = (
            (record.soa is not None, DnsRecordType.SOA, "SOA typed payload is only valid on SOA RRsets"),
            (record.mx is not None, DnsRecordType.MX, "MX typed payload is only valid on MX RRsets"),
            (record.srv is not None, DnsRecordType.SRV, "SRV typed payload is only valid on SRV RRsets"),
            (bool(record.text), DnsRecordType.TXT, "TXT text payload is only valid on TXT RRsets"),
        )
        for is_present, expected_type, error_message in payload_checks:
            if is_present and self.record_type != expected_type:
                raise ValueError(error_message)

    def _validate_address(self, address: str) -> None:
        if self.record_type not in _ADDRESS_RECORD_TYPES:
            raise ValueError("address typed payload is only valid on A or AAAA RRsets")
        if _is_unresolved_variable(address):
            return
        parsed = self._validate_ip_address(address, field_name=f"{self.record_type.value.upper()} record address")
        self._validate_address_version(parsed)

    @staticmethod
    def _validate_ip_address(address: str, *, field_name: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as e:
            raise ValueError(f"{field_name} must be a valid IP address") from e
        return parsed

    def _validate_address_version(self, parsed: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if self.record_type == DnsRecordType.A and parsed.version != 4:
            raise ValueError("A record address must be a valid IPv4 address")
        if self.record_type == DnsRecordType.AAAA and parsed.version != 6:
            raise ValueError("AAAA record address must be a valid IPv6 address")
