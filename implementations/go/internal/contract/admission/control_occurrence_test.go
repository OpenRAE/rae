package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type controlOccurrenceTestContext struct {
	records      [][]byte
	declarations []ControlDeclaration
	targets      []ControlTarget
}

func (c controlOccurrenceTestContext) ControlOccurrences() [][]byte { return c.records }
func (c controlOccurrenceTestContext) ControlDeclarations() []ControlDeclaration {
	return c.declarations
}
func (c controlOccurrenceTestContext) ControlTargets() []ControlTarget { return c.targets }

func TestControlOccurrenceJoinsCompiledDeclarationAndTransformedSource(t *testing.T) {
	e := boundTestOwner(t)
	proposal := fixtureObject(t, "fixtures/participant-runtime/participant-control-occurrence-v1/valid/proposal.json")
	var declaration ControlDeclaration
	if err := json.Unmarshal(controlJSON(t, at(proposal, "occurrence")), &declaration); err != nil {
		t.Fatal(err)
	}
	declaration.ParticipantAddress, declaration.EpisodeID = stringAt(proposal, "participant_address"), stringAt(proposal, "episode_id")
	context := controlOccurrenceTestContext{records: [][]byte{controlJSON(t, proposal)}, declarations: []ControlDeclaration{declaration}}
	i := validation.Invocation{Instance: proposal, Context: context}
	if err := validateTestDocument(t, e, "participant-control-occurrence-v1", i.Instance, i.Context); err != nil {
		t.Fatal(err)
	}
	context.declarations[0].ControllerRef = "controller.foreign"
	if err := validateTestDocument(t, e, "participant-control-occurrence-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted foreign declaration controller")
	}
	context.declarations[0] = declaration
	transformed := fixtureObject(t, "fixtures/participant-runtime/participant-control-occurrence-v1/valid/proposal.json")
	transformed["event_id"] = "control.transformed"
	transformed["provenance_refs"] = []any{at(proposal, "event_id"), "transform.sanitized"}
	occurrence := object(at(transformed, "occurrence"))
	occurrence["proposal_id"], occurrence["source_proposal_ref"], occurrence["source_proposal_revision"], occurrence["transformation_ref"] = "proposal.transformed", at(proposal, "occurrence", "proposal_id"), at(proposal, "occurrence", "proposal_revision"), "transform.sanitized"
	context.records = append(context.records, controlJSON(t, transformed))
	i.Instance, i.Context = transformed, context
	if err := validateTestDocument(t, e, "participant-control-occurrence-v1", i.Instance, i.Context); err != nil {
		t.Fatal(err)
	}
	transformed["object_marking_refs"] = []any{}
	context.records[1] = controlJSON(t, transformed)
	i.Context = context
	if err := validateTestDocument(t, e, "participant-control-occurrence-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted transformed proposal without inherited markings")
	}
}
