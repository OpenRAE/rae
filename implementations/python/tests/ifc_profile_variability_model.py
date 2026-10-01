"""Finite IFC-01–IFC-07 design projection, not a provider or wire contract.

The encoding fragment has independently releasable obligations and singleton
tokens. It is not a solver for arbitrary conservative contextual encodings.
Coverage, grants and guarantee facts are independently trusted inputs; set
inclusion represents only comparable guarantees in this synthetic experiment.
"""

from dataclasses import dataclass

from sem233_boundary_flow_model import FlowProfile, UnsupportedFlow, rewrite_coordinate


@dataclass(frozen=True)
class Requirement:
    confidentiality: frozenset[str]
    integrity: frozenset[str]
    coverage: frozenset[str]
    guarantees: frozenset[str]


@dataclass(frozen=True)
class Encoding:
    profile: FlowProfile
    confidentiality: tuple[tuple[str, str], ...]
    integrity: tuple[tuple[str, str], ...]
    digest: str = "digest:synthetic-owner-publication"

    @property
    def pin(self):
        return self.profile.profile_id, self.profile.profile_revision, self.digest


@dataclass(frozen=True)
class Support:
    profile_pin: tuple[str, str, str]
    configuration: str
    coverage: frozenset[str]
    guarantees: frozenset[str]
    resolved: bool = True


def _expresses(required, pairs, universe, unresolved):
    mapping = dict(pairs)
    if len(mapping) != len(pairs) or not required <= mapping.keys():
        return False
    targets = {mapping[item] for item in required}
    return len(targets) == len(required) and targets <= universe - {unresolved}


def admit(requirement, encoding, support):
    """Project expressibility then CA-04 realization; no effect is dispatched."""
    profile = encoding.profile
    if not (
        _expresses(
            requirement.confidentiality,
            encoding.confidentiality,
            profile.confidentiality_universe,
            "conf:deny-unresolved",
        )
        and _expresses(requirement.integrity, encoding.integrity, profile.integrity_universe, "int:deny-unresolved")
    ):
        raise UnsupportedFlow("expression unsupported")
    if not (
        support.resolved
        and support.profile_pin == encoding.pin
        and support.configuration
        and requirement.coverage <= support.coverage
        and requirement.guarantees <= support.guarantees
    ):
        raise UnsupportedFlow("realization unsupported")
    return support


def check_execution(admitted, observed):
    if not observed.resolved or (observed.profile_pin, observed.configuration) != (
        admitted.profile_pin,
        admitted.configuration,
    ):
        return "unsupported"
    if not admitted.coverage <= observed.coverage or not admitted.guarantees <= observed.guarantees:
        return "weakened"
    return "resolved"


@dataclass(frozen=True)
class Grant:
    authority: str
    confidentiality: frozenset[str]
    integrity: frozenset[str]
    sink: str
    cut: str
    source: str
    profile: tuple[str, str]


def release(
    profile,
    source,
    grant,
    *,
    result_ref,
    operation,
    confidentiality=frozenset(),
    integrity=frozenset(),
    sink="sink:action",
    cut="cut:1",
):
    """A trusted exact-context grant must cover every discharged obligation.

    The reused algebra checks fresh identity, operation/coordinate separation,
    membership and immutable provenance. Grant acquisition is outside this model.
    """
    if not (
        (grant.sink, grant.cut) == (sink, cut)
        and grant.source == source.value_ref
        and grant.profile == (profile.profile_id, profile.profile_revision)
        and confidentiality <= grant.confidentiality
        and integrity <= grant.integrity
    ):
        raise UnsupportedFlow("release authority does not cover the exact obligation and cut")
    return rewrite_coordinate(
        profile,
        source,
        result_ref=result_ref,
        operation=operation,
        remove_confidentiality=confidentiality,
        remove_integrity=integrity,
        authority_ref=grant.authority,
        sink_ref=sink,
        state_cut_ref=cut,
    )
