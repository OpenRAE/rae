package processor_test

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type foreignParticipantFragment struct{ admission.Fragment }

func (foreignParticipantFragment) Document() any { panic("foreign fragment called") }
func participantActionShape(t *testing.T, model processor.RuntimeModel, address string) string {
	t.Helper()
	for _, resource := range model.View().ParticipantResources {
		if resource.Address != address {
			continue
		}
		var output struct {
			Shape string `json:"argument_shape_ref"`
		}
		if err := json.Unmarshal(resource.Payload.JSON(), &output); err != nil {
			t.Fatal(err)
		}
		return output.Shape
	}
	t.Fatal("compiled action missing")
	return ""
}
func participantAPIErrorIsValueFree(t *testing.T, err error, findings []diagnostic.Diagnostic) {
	t.Helper()
	if err == nil || strings.Contains(err.Error(), "private-canary") || len(findings) > 0 {
		t.Fatalf("invalid input result=%v err=%v", findings, err)
	}
}
func TestParticipantRelationsRejectReplacedFragmentsAndWrongProfiles(t *testing.T) {
	vectors := participantRelations(t)
	model := toolSupportModel(t, toolSupportSource{Text: vectors.Sources["action"]})
	shape := participantActionShape(t, model, "participant.action-contract.scan")
	valid, err := participantFragment(t, admission.RealizationValue, []byte(`{}`))
	if err != nil {
		t.Fatal(err)
	}
	for _, input := range []admission.Fragment{nil, foreignParticipantFragment{valid}, valid} {
		findings, err := processor.ParticipantActionResultViolations(model, "participant.action-contract.scan", input)
		participantAPIErrorIsValueFree(t, err, findings)
	}
	for _, input := range []admission.Fragment{nil, foreignParticipantFragment{valid}} {
		_, err := processor.ResolveParticipantActionArguments(model, "participant.action-contract.scan", shape, "proposal", input)
		participantAPIErrorIsValueFree(t, err, nil)
		findings, err := processor.ParticipantTemporalStateMachineViolations(input)
		participantAPIErrorIsValueFree(t, err, findings)
		findings, err = processor.ParticipantBehaviorHistoryViolations(model, "participant.behavior.red-agent", input, nil)
		participantAPIErrorIsValueFree(t, err, findings)
		findings, err = processor.ParticipantJointActionViolations(input)
		participantAPIErrorIsValueFree(t, err, findings)
	}
	for _, raw := range []string{`null`, `{}`, `"private-canary"`} {
		input, err := participantFragment(t, admission.RealizationValue, []byte(raw))
		if err != nil {
			t.Fatal(err)
		}
		findings, err := processor.ParticipantTemporalStateMachineViolations(input)
		participantAPIErrorIsValueFree(t, err, findings)
	}
}

func TestParticipantHistoryBoundsAggregateMetadataWork(t *testing.T) {
	vectors := participantHistoryReference(t)
	model := toolSupportModel(t, toolSupportSource{Text: vectors.Sources["budget"]})
	baseline := string(vectors.History[0].Input)
	for _, count := range []int{130, 210} {
		history := []json.RawMessage{}
		for index := range count {
			var group []json.RawMessage
			input := strings.ReplaceAll(baseline, "scan-0001", fmt.Sprintf("scan-%04d", index+10))
			if err := json.Unmarshal([]byte(input), &group); err != nil {
				t.Fatal(err)
			}
			history = append(history, group...)
		}
		input, err := participantFragment(t, admission.RealizationValue, requireJSON(t, history))
		if err != nil {
			t.Fatal(err)
		}
		findings, err := processor.ParticipantBehaviorHistoryViolations(model, "participant.behavior.red-agent", input, nil)
		if count == 130 {
			if err != nil {
				t.Fatalf("inside metadata budget refused: %v", err)
			}
		} else {
			participantAPIErrorIsValueFree(t, err, findings)
		}
	}
}
func TestParticipantArgumentResolutionRetainsImmutableNativeMeaning(t *testing.T) {
	vectors := participantRelations(t)
	test := vectors.Arguments[0]
	model := toolSupportModel(t, toolSupportSource{Text: vectors.Sources[test.Source]})
	input, err := participantFragment(t, admission.RealizationValue, test.Input)
	if err != nil {
		t.Fatal(err)
	}
	first, err := processor.ResolveParticipantActionArguments(model, test.Address, test.Shape, test.Proposal, input)
	if err != nil {
		t.Fatal(err)
	}
	participantMutableFragmentDocument(t, first)["proposal_ref"] = "changed"
	participantMutableFragmentDocument(t, input)["target"] = "private-canary"
	model.Document()["action_contracts"] = nil
	second, err := processor.ResolveParticipantActionArguments(model, test.Address, test.Shape, test.Proposal, input)
	if err != nil {
		t.Fatal(err)
	}
	assertReferenceJSON(t, "sealed first result", requireJSON(t, first.Document()), test.Expected)
	assertReferenceJSON(t, "repeat result", requireJSON(t, second.Document()), test.Expected)
	for _, proposal := range []string{"", string([]byte{0xff}), strings.Repeat("x", (1<<20)+1)} {
		_, err := processor.ResolveParticipantActionArguments(model, test.Address, test.Shape, proposal, input)
		participantAPIErrorIsValueFree(t, err, nil)
	}
}
func TestParticipantArgumentResolutionBoundsAggregateDomainWork(t *testing.T) {
	allowed := make([]string, 1000)
	for index := range allowed {
		allowed[index] = fmt.Sprintf("value-%04d", index)
	}
	definition := map[string]any{"value_type": "string", "cardinality": "many", "allowed_values": allowed, "unique_items": false, "normalization": "identity", "normalization_disclosure_ref": "normalization", "omission": "reject", "omission_disclosure_ref": "omission", "loss_disclosure_ref": "loss"}
	contract := map[string]any{"semantic_version": "1.0.0", "behavioral_granularity": "atomic", "procedure_basis": "bounded values", "realization_profile": "abstract", "fidelity_claim": "preserves values", "arguments": map[string]any{"values": definition}}
	contract["preconditions"] = []any{map[string]any{"precondition_id": "available", "precondition_class": "realization", "description": "declared support", "support_refs": []string{"backend.bounded"}}}
	contract["effects"] = []any{map[string]any{"effect_id": "none", "effect_class": "no_effect", "description": "abstract normalization"}}
	contract["failure_classes"] = []string{"unknown"}
	source := requireJSON(t, map[string]any{"name": "bounded-action", "action_contracts": map[string]any{"select": contract}})
	model := toolSupportModel(t, toolSupportSource{Text: string(source)})
	address := "participant.action-contract.select"
	shape := participantActionShape(t, model, address)
	for _, count := range []int{99, 100} {
		items := slices.Repeat([]string{allowed[len(allowed)-1]}, count)
		input, err := participantFragment(t, admission.RealizationValue, requireJSON(t, map[string]any{"values": items}))
		if err != nil {
			t.Fatal(err)
		}
		result, err := processor.ResolveParticipantActionArguments(model, address, shape, "proposal", input)
		if count == 99 {
			if err != nil || result == nil {
				t.Fatalf("inside work ceiling refused: %v", err)
			}
		} else {
			participantAPIErrorIsValueFree(t, err, nil)
			if result != nil {
				t.Fatal("over-budget input returned a partial normalized result")
			}
		}
	}
}
func participantMutableFragmentDocument(t *testing.T, input admission.Fragment) map[string]any {
	t.Helper()
	result, ok := input.Document().(map[string]any)
	if !ok {
		t.Fatal("expected native object fragment")
	}
	return result
}

func TestParticipantArgumentShapeCommitsToAdmittedDomains(t *testing.T) {
	vectors := participantRelations(t)
	source := vectors.Sources["arguments"]
	first := toolSupportModel(t, toolSupportSource{Text: source})
	changed := strings.Replace(source, `"maximum": 3`, `"maximum": 4`, 1)
	second := toolSupportModel(t, toolSupportSource{Text: changed})
	address := "participant.action-contract.respond"
	if changed == source || participantActionShape(t, first, address) == participantActionShape(t, second, address) {
		t.Fatal("changed maximum did not change the compiled argument pin")
	}
	for _, test := range []struct{ old, new string }{
		{`"value_type": "reference"`, `"backend_command": "private-canary", "value_type": "reference"`},
		{`"allowed_values": ["hostname", "owner", "status"]`, `"allowed_values": [" hostname ", "hostname"]`},
		{`"allowed_values": ["hostname", "owner", "status"]`, `"allowed_values": [" x "], "min_length": 2`},
	} {
		invalid := strings.Replace(source, test.old, test.new, 1)
		if invalid == source {
			t.Fatal("invalid-domain test did not change input")
		}
		if _, err := sdl.Parse([]byte(invalid), sdl.DefaultParseOptions()); err == nil {
			t.Fatal("invalid authored argument shape admitted")
		}
	}
}
