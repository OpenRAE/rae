"""Consumer constraints keep private identity exact across owning boundaries."""

from copy import deepcopy

import pytest
from raes._base import is_variable_ref
from raes.image_provenance import ImageAttestation, ImageVerificationStatus
from raes.runtime_forwarding_agent import RelationshipForwardingEdge, RuntimeForwardingShipTarget
from raes.validator._relationships import _RelationshipsMixin


class _AgreementBoundary(_RelationshipsMixin):
    _is_unresolved_var = staticmethod(is_variable_ref)

    def __init__(self):
        self.errors = []

    def _err(self, message):
        self.errors.append(message)


def test_private_attestation_format_retains_identity_without_claiming_verification():
    attestation = ImageAttestation(attestation_type="x-owner:format")
    assert attestation.attestation_type == "x-owner:format"
    assert attestation.verification is not ImageVerificationStatus.VERIFIED
    assert ImageAttestation.model_validate_json(attestation.model_dump_json()).attestation_type == "x-owner:format"


@pytest.mark.parametrize("actual,accepted", [("x-owner:wire", True), ("x-owner:other", False), ("syslog", False)])
def test_forwarding_protocol_agreement_compares_private_identities(actual, accepted):
    boundary = _AgreementBoundary()
    target = RuntimeForwardingShipTarget(target_id="target", protocol="x-owner:wire")
    edge = RelationshipForwardingEdge(forwarder_ref="forwarder", protocol=actual)
    boundary._check_forwarding_edge_protocol_agreement(edge, [target], "forwarder", "edge")
    assert (not boundary.errors) is accepted


def test_dns_numeric_identity_remains_exact_under_an_open_parent():
    from raes import parse_sdl
    from raes_contracts.realization_structure import evaluate_realization_constraint
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.semantics.realization_concerns import project_realization_concern

    scenario = parse_sdl("""
name: numeric-identity
realization: {default: open}
nodes:
  host:
    type: compute
    runtime:
      dns_services:
        - dns_service_id: dns
          zones:
            - zone_id: zone
              name: example.test
              rrsets:
                - rrset_id: record
                  owner: example.test
                  record_type: other
                  type_code: 65280
                  records: [{rdata: opaque-content}]
""")
    model = compile_runtime_model(scenario)
    requirement = next(r for r in model.realization_requirements if r.requirement_kind == "runtime-dns-services")
    assert requirement.constraint_document is not None
    projected = project_realization_concern(
        "runtime-dns-services", scenario.nodes["host"].runtime.dns_services, recursive=True
    )
    assert evaluate_realization_constraint(requirement.constraint_document, projected).conformant
    changed = deepcopy(projected)
    changed[0]["zones"][0]["rrsets"][0]["type_code"] = 65281
    assert not evaluate_realization_constraint(requirement.constraint_document, changed).conformant
