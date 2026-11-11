"""Enum vocabularies for the ``runtime.forwarding_agents`` family (SCN-010 §5.5).

Split out of ``runtime_forwarding_agent.py`` so neither source file exceeds the
ADR-015 600-line cap. Every enum here is an OPEN taxonomy carrying both
``unknown`` and ``other`` sentinels, except the small CLOSED structural sets
called out per the enum-sentinel discipline (§6): the enrollment-identity
classification (a fixed redaction lattice) carries neither.
"""

from enum import Enum

__all__ = [
    "RuntimeForwardingAgentImplementation",
    "RuntimeForwardingAgentKind",
    "RuntimeForwardingAgentOwnershipRole",
    "RuntimeForwardingBufferCrypto",
    "RuntimeForwardingEnrollmentClassification",
    "RuntimeForwardingParseFormat",
    "RuntimeForwardingProtocol",
    "RuntimeForwardingReloadChannelKind",
    "RuntimeForwardingSettingClassification",
    "RuntimeForwardingSettingProvenance",
    "RuntimeForwardingSourceKind",
    "RuntimeForwardingTransformKind",
]


class RuntimeForwardingAgentImplementation(str, Enum):
    """Observed product family for a forwarding / intel-sync agent (OPEN)."""

    FILEBEAT = "filebeat"
    WAZUH_AGENT = "wazuh_agent"
    FLUENT_BIT = "fluent_bit"
    FLUENTD = "fluentd"
    LOGSTASH = "logstash"
    VECTOR = "vector"
    RSYSLOG = "rsyslog"
    NXLOG = "nxlog"
    OTEL_COLLECTOR = "otel_collector"
    MISP_SURICATA_SYNC = "misp_suricata_sync"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingAgentKind(str, Enum):
    """Portable forwarding-agent role discriminator (OPEN per the verdict)."""

    LOG_FORWARDER = "log_forwarder"
    CONTENT_SYNC = "content_sync"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingAgentOwnershipRole(str, Enum):
    """Closed ownership of an agent relative to the system under test."""

    SYSTEM_UNDER_TEST = "system_under_test"
    MEASUREMENT_APPARATUS = "measurement_apparatus"


class RuntimeForwardingSourceKind(str, Enum):
    """Portable provenance family for a forwarder input source (OPEN)."""

    TAILED_PATH = "tailed_path"
    API_PULL = "api_pull"
    QUEUE = "queue"
    SOCKET = "socket"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingParseFormat(str, Enum):
    """Portable on-the-wire / on-disk parse format of a source (OPEN)."""

    JSON = "json"
    SYSLOG = "syslog"
    EVE_JSON = "eve_json"
    CEF = "cef"
    LEEF = "leef"
    CSV = "csv"
    TEXT = "text"
    STIX = "stix"
    MISP_JSON = "misp_json"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingTransformKind(str, Enum):
    """Portable transform family applied between source and ship target (OPEN)."""

    PASSTHROUGH = "passthrough"
    PARSE = "parse"
    IOC_TO_RULE = "ioc_to_rule"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingProtocol(str, Enum):
    """Portable wire protocol of a ship target (OPEN)."""

    SYSLOG = "syslog"
    SYSLOG_TLS = "syslog_tls"
    SYSLOG_TCP = "syslog_tcp"
    BEATS = "beats"
    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"
    UDP = "udp"
    KAFKA = "kafka"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingBufferCrypto(str, Enum):
    """Portable at-rest / in-transit crypto of a buffer policy (OPEN)."""

    NONE = "none"
    AES = "aes"
    TLS = "tls"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingReloadChannelKind(str, Enum):
    """Portable control / reload channel family for a downstream consumer (OPEN)."""

    UNIX_SOCKET = "unix_socket"
    SIGNAL = "signal"
    HTTP_API = "http_api"
    CLI = "cli"
    FILE_DROP = "file_drop"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingSettingProvenance(str, Enum):
    """Portable provenance of an observed forwarding setting (OPEN)."""

    CONFIGURATION_FILE = "configuration_file"
    ENVIRONMENT = "environment"
    COMMAND_LINE = "command_line"
    DEFAULT = "default"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeForwardingEnrollmentClassification(str, Enum):
    """Redaction class for a ship-target enrollment identity (CLOSED).

    A fixed structural lattice — an enrollment credential is either absent
    (``none``) or present-but-not-recorded (``redacted`` / ``operator_secret``).
    Raw enrollment-key material is never carried; per the enum-sentinel
    discipline this closed set carries no ``unknown`` / ``other`` tail.
    """

    NONE = "none"
    REDACTED = "redacted"
    OPERATOR_SECRET = "operator_secret"  # noqa: S105


class RuntimeForwardingSettingClassification(str, Enum):
    """Redaction class for an observed forwarding setting value (CLOSED).

    The fixed structural redaction lattice for a setting: a plain value, a
    present-but-not-recorded secret, or an operator-only secret. Carries no
    open tail by the enum-sentinel discipline.
    """

    PLAIN = "plain"
    REDACTED = "redacted"
    OPERATOR_SECRET = "operator_secret"  # noqa: S105
