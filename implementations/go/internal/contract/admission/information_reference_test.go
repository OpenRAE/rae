package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type informationOwnerReference struct {
	Record  json.RawMessage `json:"record"`
	Sources []struct {
		ContractID string          `json:"contract_id"`
		Reference  string          `json:"reference"`
		Document   json.RawMessage `json:"document"`
		Coordinate json.RawMessage `json:"coordinate"`
	} `json:"sources"`
	Histories map[string][]json.RawMessage `json:"histories"`
	Proofs    map[string]string            `json:"proofs"`
	Surfaces  []json.RawMessage            `json:"surfaces"`
	Admitted  bool                         `json:"admitted"`
}

func TestInformationSourceAndSurfaceCoordinatesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	count := 0
	for shard := 1; shard <= 2; shard++ {
		var reference struct {
			Cases []informationOwnerReference `json:"cases"`
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/information-owner-verdicts-%02d.json", shard), &reference)
		for _, c := range reference.Cases {
			count++
			t.Run(fmt.Sprintf("%02d", count), func(t *testing.T) {
				context := recordedInformationContext(t, c)
				admitted, err := e.Validate("participant-information-state-record-v1", c.Record, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, context)
				if (err == nil) != c.Admitted {
					t.Fatalf("information owner differs from Python (admitted=%v): %v", c.Admitted, err)
				}
				if err != nil && admitted.ContractID() != "" {
					t.Fatal("refusal returned an admitted value")
				}
			})
		}
	}
	if count != 37 {
		t.Fatal("independent information-state inventory changed")
	}
}

func recordedInformationContext(t *testing.T, c informationOwnerReference) informationTestContext {
	t.Helper()
	context := informationTestContext{proofs: c.Proofs, surfaces: flowRawList(c.Surfaces), histories: map[string][][]byte{}}
	for name, rows := range c.Histories {
		context.histories[name] = flowRawList(rows)
	}
	for _, source := range c.Sources {
		coordinate := decodeRuleObject(t, string(source.Coordinate))
		context.sources = append(context.sources, InformationSource{ContractID: source.ContractID, Reference: source.Reference, Document: source.Document, Coordinate: InformationSourceCoordinate{
			ParticipantAddress: stringAt(coordinate, "participant_address"), EpisodeID: stringAt(coordinate, "episode_id"), AudienceScopeRef: stringAt(coordinate, "audience_scope_ref"), VisibilityProjectionRef: stringAt(coordinate, "visibility_projection_ref"), ProjectionPolicyRevision: stringAt(coordinate, "projection_policy_revision"), RedactionPolicyRef: stringAt(coordinate, "redaction_policy_ref"), RedactionPolicyRevision: stringAt(coordinate, "redaction_policy_revision"), StateCut: controlJSON(t, at(coordinate, "state_cut")),
		}})
	}
	return context
}
