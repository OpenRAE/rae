package realization

import (
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestPlannedReadbackFacadesRefuseCorruptTransportBeforeGrantingProvenance(t *testing.T) {
	invalid := binding.ProvisioningPlanV1{}
	if _, err := PlannedAuthorityDiagnostics(invalid, EvaluationOptions{}); err == nil {
		t.Fatal("invalid plan granted authority diagnostics")
	}
	if _, err := PlannedRequirements(invalid); err == nil {
		t.Fatal("invalid plan recovered concern authority")
	}
	if result, err := EvaluatePlanned(invalid, binding.RuntimeSnapshotV1{}, EvaluationOptions{}); err == nil || len(result.Provenance) != 0 {
		t.Fatal("invalid plan generated readback provenance")
	}
	if _, err := CleanupPlannedDiagnostics(invalid, binding.RuntimeSnapshotV1{}, nil, EvaluationOptions{}); err == nil {
		t.Fatal("invalid plan granted cleanup authority")
	}
}

func TestProjectionRefusalsPreserveOperationalFaultsAndNeverProduceProvenance(t *testing.T) {
	requirement := Requirement{Address: "provision.node.host", Kind: "node-source"}
	unexpected := fault.New(fault.Operational, "fixture-operation", nil)
	finding, provenance, err := projectionFailureAsApproximation(requirement, unexpected)
	if !errors.Is(err, unexpected) || finding != nil || provenance != nil {
		t.Fatal("operational failure became successful approximation")
	}
	finding, provenance, err = projectionFailureAsApproximation(requirement, invalidRealization())
	if err != nil || finding == nil || provenance != nil {
		t.Fatal("invalid artifact projection granted provenance")
	}
	if _, err := plannedEvaluationFailure(unexpected, evaluatedPlan{}); !errors.Is(err, unexpected) {
		t.Fatal("planned evaluation swallowed an operational error")
	}
	if _, err := plannedViewFailure(unexpected, evaluatedPlan{}); !errors.Is(err, unexpected) {
		t.Fatal("planned view swallowed an operational error")
	}
}

func TestArtifactDeclarationsRefuseOversizedOrUnverifiedSelection(t *testing.T) {
	if _, err := ArtifactSupport(make([]Requirement, 16385), binding.BackendManifestV2{}, nil); err == nil {
		t.Fatal("unbounded artifact requirement batch accepted")
	}
	for _, input := range []any{func() {}, true} {
		if _, err := decodeArtifactCapability(input); err == nil {
			t.Fatal("invalid artifact capability accepted")
		}
	}
	unknown := "unknown"
	if !artifactCandidateInvalid(artifactContract{}, artifactSatisfaction{Candidate: &unknown}, ArtifactAvailability{}) {
		t.Fatal("undeclared artifact candidate accepted")
	}
	if !artifactSpecificationInvalid(artifactContract{}, artifactSatisfaction{Specification: &unknown}, ArtifactAvailability{}) {
		t.Fatal("undeclared artifact specification accepted")
	}
	if !artifactSpecificationInvalid(artifactContract{}, artifactSatisfaction{SpecificationDigest: &unknown}, ArtifactAvailability{}) {
		t.Fatal("unbound artifact specification digest accepted")
	}
}

func TestRuntimeReconstructionRefusesUnknownConcernsAndMismatchedNativeShapes(t *testing.T) {
	if _, err := projectTypedRuntimeOptions("unknown", nil, true, true, true); err == nil {
		t.Fatal("unknown runtime concern accepted")
	}
	if _, err := projectTypedRuntimeOptions("runtime-environment", []any{map[string]any{"value_present": "true"}}, true, true, true); err == nil {
		t.Fatal("invalid runtime marker reached normalization")
	}
	if _, err := serviceManagerPresence([]any{}, []any{true}); err == nil {
		t.Fatal("service-manager projection changed collection cardinality")
	}
	if _, err := serviceManagerPresence(true, nil); err != nil {
		t.Fatal("absent service-manager view became a failure")
	}
	for _, input := range []any{true, []any{map[string]any{"repository_refs": true}}} {
		if projectSoftwareRepositoryRefs(input, false) == nil {
			t.Fatal("invalid software repository references accepted")
		}
	}
}
