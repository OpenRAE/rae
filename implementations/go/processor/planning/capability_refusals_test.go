package planning

import (
	"encoding/json"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func capabilityCodes(findings []diagnostic.Diagnostic) []string {
	result := make([]string, len(findings))
	for i, finding := range findings {
		result[i] = finding.Code
	}
	return result
}

func TestOrchestrationCapabilitiesRequireEveryUsedSectionAndFeature(t *testing.T) {
	kinds := map[string][]processor.Resource{
		"inject-binding": {{}}, "event": {{UsesAssertionRefs: true}},
		"workflow": {{RequiredFeatures: []string{"parallel", "parallel"}, WorkflowStatePredicateFeatures: []string{"completed"}}},
	}
	for _, raw := range []json.RawMessage{nil, json.RawMessage(`null`)} {
		findings, err := orchestrationDiagnostics(kinds, raw)
		if err != nil || !slices.Equal(capabilityCodes(findings), []string{"orchestrator.missing"}) {
			t.Fatalf("missing orchestrator: %+v %v", findings, err)
		}
	}
	findings, err := orchestrationDiagnostics(kinds, json.RawMessage(`{}`))
	want := []string{"orchestrator.unsupported-section", "orchestrator.unsupported-section", "orchestrator.unsupported-section", "orchestrator.workflows-unsupported", "orchestrator.workflow-feature-unsupported", "orchestrator.assertion-refs-unsupported", "orchestrator.step-state-predicate-feature-unsupported", "orchestrator.inject-bindings-unsupported"}
	if err != nil || !slices.Equal(capabilityCodes(findings), want) {
		t.Fatalf("orchestration refusals: %v %v", capabilityCodes(findings), err)
	}
	caps := orchestratorCapabilities{SupportedSections: []string{"injects", "events", "workflows"}, SupportsWorkflows: true, SupportedWorkflowFeatures: []string{"parallel"}, SupportsAssertionRefs: true, SupportedWorkflowStatePredicates: []string{"completed"}, SupportsInjectBindings: true}
	if findings, err := orchestrationDiagnostics(kinds, rawProjection(caps)); err != nil || len(findings) != 0 {
		t.Fatalf("supported orchestration refused: %+v %v", findings, err)
	}
	if _, err := orchestrationDiagnostics(kinds, json.RawMessage(`[]`)); err == nil {
		t.Fatal("invalid capability shape accepted")
	}
}

func TestEvaluationCapabilitiesRequirePropositionEvidenceAndTemporalAuthority(t *testing.T) {
	facts := &processor.EvaluationFacts{PredicateKind: "comparison", Quantifier: "all", DeferredExpected: true, RequiredTimeDomain: "simulation", EvidenceChannels: []string{"submission"}, UnresolvedEvidenceChannelRefs: []string{"missing"}}
	kinds := map[string][]processor.Resource{"objective": {{}}, "proposition": {{Address: "evaluation.proposition.result", Evaluation: facts}}}
	findings, err := evaluationDiagnostics(kinds, nil)
	if err != nil || !slices.Equal(capabilityCodes(findings), []string{"evaluator.missing"}) {
		t.Fatalf("missing evaluator: %+v %v", findings, err)
	}
	supportsObjectives := false
	caps := evaluatorCapabilities{SupportedSections: []string{"propositions"}, SupportsObjectives: &supportsObjectives}
	findings, err = evaluationDiagnostics(kinds, rawProjection(caps))
	want := []string{"evaluator.unsupported-section", "evaluator.objectives-unsupported", "evaluator.unsupported-predicate-family", "evaluator.unsupported-deferred-expected-comparison", "evaluator.unsupported-quantifier", "evaluator.evidence-channel-unresolved", "evaluator.unsupported-evidence-channel", "evaluator.unsupported-time-domain"}
	if err != nil || !slices.Equal(capabilityCodes(findings), want) {
		t.Fatalf("evaluation refusals: %v %v", capabilityCodes(findings), err)
	}
	facts.UnresolvedEvidenceChannelRefs = nil
	caps = evaluatorCapabilities{SupportedSections: []string{"propositions", "objectives"}, SupportedPredicateFamilies: []string{"comparison"}, SupportedQuantifiers: []string{"all"}, SupportsDeferredExpectedComparison: true, SupportedEvidenceChannels: []string{"submission"}, SupportedTimeDomains: []string{"simulation"}}
	if findings, err := evaluationDiagnostics(kinds, rawProjection(caps)); err != nil || len(findings) != 0 {
		t.Fatalf("supported evaluation refused: %+v %v", findings, err)
	}
	kinds["proposition"][0].Evaluation = nil
	if _, err := evaluationDiagnostics(kinds, rawProjection(caps)); err == nil {
		t.Fatal("unowned proposition facts accepted")
	}
	if _, err := evaluationDiagnostics(kinds, json.RawMessage(`[]`)); err == nil {
		t.Fatal("invalid evaluator shape accepted")
	}
}

func TestTimeCapabilityLimitsRefuseFractionalAndMalformedDeclarations(t *testing.T) {
	model := processor.CompiledScenario{HasTimeModel: true, TimeModel: processor.CompiledTimeModel{
		Domains: []processor.TimeDomain{{Kind: "simulation"}}, Clocks: []processor.Clock{{AuthorityKind: "controller", SupportsPause: true, SupportsJump: true}},
		Mappings: []processor.TimeMapping{{Kind: "affine"}}, Constraints: []processor.TemporalConstraint{{Kind: "deadline"}},
		ProgressionPolicies: []processor.TimePolicy{{AdvancementMode: "step", SynchronizationMode: "barrier", ResetBehavior: "origin", ReplayBehavior: "recorded"}},
	}}
	if findings, err := timeDiagnostics(model, nil); err != nil || len(findings) != 1 {
		t.Fatalf("missing time authority: %+v %v", findings, err)
	}
	if _, err := timeDiagnostics(model, json.RawMessage(`[]`)); err == nil {
		t.Fatal("invalid time capability shape accepted")
	}
	for _, limit := range []string{"0.5", "true"} {
		if _, err := timeDiagnostics(model, json.RawMessage(`{"max_time_domains":`+limit+`}`)); err == nil {
			t.Fatalf("invalid time limit %s accepted", limit)
		}
	}
	zero := json.Number("0")
	caps := timeCapabilities{MaxDomains: &zero, MaxClocks: &zero}
	findings, err := timeDiagnostics(model, rawProjection(caps))
	if err != nil || len(findings) != 15 {
		t.Fatalf("missing time capability obligations: %+v %v", findings, err)
	}
	for _, finding := range findings {
		if finding.Code != "time.unsupported-capability" || finding.Address != "time.model" {
			t.Fatalf("time refusal lost its owner: %+v", finding)
		}
	}
}
