package processor

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type evaluationResultContract struct {
	StateSchemaVersion string `json:"state_schema_version"`
	ResourceType       string `json:"resource_type"`
	SupportsPassed     bool   `json:"supports_passed"`
	SupportsScore      bool   `json:"supports_score"`
	FixedMaxScore      *int   `json:"fixed_max_score"`
}
type evaluationExecutionContract struct {
	StateSchemaVersion string   `json:"state_schema_version"`
	ResourceType       string   `json:"resource_type"`
	AllowedStatuses    []string `json:"allowed_statuses"`
	HistoryEventTypes  []string `json:"history_event_types"`
	RequiresStartEvent bool     `json:"requires_start_event"`
}

func evaluationContracts(kind string) (evaluationResultContract, evaluationExecutionContract) {
	return evaluationResultContract{StateSchemaVersion: "evaluation-result-state/v1", ResourceType: kind, SupportsPassed: kind == termConditionBinding || kind == termObjective}, evaluationExecutionContract{StateSchemaVersion: "evaluation-result-state/v1", ResourceType: kind, AllowedStatuses: []string{"pending", "running", "ready", "failed"}, HistoryEventTypes: []string{"evaluation_started", "evaluation_updated", "evaluation_ready", "evaluation_failed"}, RequiresStartEvent: true}
}
func (state *compilerState) compilePropositions() {
	model := state.input.model
	propositions := fieldValue(model.Propositions)
	evidence := fieldValue(model.EvidenceRequirements)
	for _, name := range orderedNames(propositions, state.names(termPropositions)) {
		proposition := propositions[name]
		channels, unresolved := []string{}, []string{}
		for _, ref := range fieldValue(proposition.EvidenceRequirements) {
			channel := rawString(fieldValue(evidence[ref].Channel))
			if channel == "" {
				unresolved = append(unresolved, ref)
			} else {
				channels = append(channels, channel)
			}
		}
		slices.Sort(channels)
		channels = slices.Compact(channels)
		var predicate struct {
			Kind         string          `json:"kind"`
			ExpectedFrom json.RawMessage `json:"expected_from"`
		}
		if err := json.Unmarshal(fieldValue(proposition.Predicate), &predicate); err != nil {
			state.err = invalidCompiled()
			return
		}
		basis := string(fieldValue(proposition.Basis))
		timeDomain := ""
		if basis == "observed_state" {
			timeDomain = "scenario_time"
		}
		addr := state.address(termEvaluation, termProposition, name)
		payload := struct {
			Name                          string          `json:"name"`
			Spec                          json.RawMessage `json:"spec"`
			SubjectAddresses              []string        `json:"subject_addresses"`
			PredicateKind                 string          `json:"predicate_kind"`
			Quantifier                    string          `json:"quantifier"`
			EvaluationBasis               string          `json:"evaluation_basis"`
			EvidenceRequirementRefs       []string        `json:"evidence_requirement_refs"`
			EvidenceChannels              []string        `json:"evidence_channels"`
			UnresolvedEvidenceChannelRefs []string        `json:"unresolved_evidence_channel_refs"`
			RequiredTimeDomain            string          `json:"required_time_domain"`
		}{name, rawJSON(proposition), state.runtimeAddresses(fieldValue(proposition.Subjects)), predicate.Kind, string(fieldValue(proposition.Quantifier)), basis, nonNilStrings(fieldValue(proposition.EvidenceRequirements)), channels, unresolved, timeDomain}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termEvaluation, Kind: termProposition, Payload: state.payload(payload), Evaluation: &EvaluationFacts{PredicateKind: predicate.Kind, Quantifier: string(fieldValue(proposition.Quantifier)), DeferredExpected: len(predicate.ExpectedFrom) > 0 && string(predicate.ExpectedFrom) != termNull, EvaluationBasis: basis, EvidenceChannels: channels, UnresolvedEvidenceChannelRefs: unresolved, RequiredTimeDomain: timeDomain}})
	}
}
func (state *compilerState) compileAssertions() {
	assertions := fieldValue(state.input.model.Assertions)
	for _, name := range orderedNames(assertions, state.names(termAssertions)) {
		assertion := assertions[name]
		propositionAddress := state.address(termEvaluation, termProposition, fieldValue(assertion.Proposition))
		role := string(fieldValue(assertion.Role))
		payload := struct {
			Name               string          `json:"name"`
			Spec               json.RawMessage `json:"spec"`
			PropositionAddress string          `json:"proposition_address"`
			Role               string          `json:"role"`
			Polarity           string          `json:"polarity"`
		}{name, rawJSON(assertion), propositionAddress, role, string(fieldValue(assertion.Polarity))}
		state.model.Resources = append(state.model.Resources, Resource{Address: state.address(termEvaluation, termAssertion, name), Name: name, Domain: termEvaluation, Kind: termAssertion, OrderingDependencies: []string{propositionAddress}, RefreshDependencies: []string{propositionAddress}, Payload: state.payload(payload), Evaluation: &EvaluationFacts{Role: role}})
	}
}
func (state *compilerState) compileConditionBindings() {
	model := state.input.model
	nodes := fieldValue(model.Nodes)
	conditions := fieldValue(model.Conditions)
	propositions := fieldValue(model.Propositions)
	findings := []diagnostic.Diagnostic{}
	for _, nodeName := range orderedNames(nodes, state.names(termNodes)) {
		node := nodes[nodeName]
		if string(fieldValue(node.Type)) != termCompute {
			continue
		}
		bindings := fieldValue(node.Conditions)
		nodeAddr := state.nodeAddress(nodeName)
		for _, name := range orderedNames(bindings, state.input.order["/nodes/"+escapePointer(nodeName)+"/conditions"]) {
			template, exists := conditions[name]
			if !exists {
				findings = append(findings, compileDiagnostic("evaluation.condition-template-ref-unbound", termEvaluation, nodeAddr, "Condition binding '"+name+"' on node '"+nodeName+"' does not resolve to a declared condition template."))
				continue
			}
			role := bindings[name]
			addr := state.address(termEvaluation, "condition", nodeName, name)
			propositionName := fieldValue(template.Proposition)
			propositionAddr := ""
			ordering := []string{}
			if propositionName != "" {
				propositionAddr = state.address(termEvaluation, termProposition, propositionName)
				if _, exists := propositions[propositionName]; exists {
					ordering = append(ordering, propositionAddr)
				}
			}
			resultContract, executionContract := evaluationContracts(termConditionBinding)
			payload := struct {
				Name               string                      `json:"name"`
				Spec               any                         `json:"spec"`
				NodeName           string                      `json:"node_name"`
				NodeAddress        string                      `json:"node_address"`
				ConditionName      string                      `json:"condition_name"`
				TemplateAddress    string                      `json:"template_address"`
				RoleName           string                      `json:"role_name"`
				PropositionAddress string                      `json:"proposition_address"`
				ResultContract     evaluationResultContract    `json:"result_contract"`
				ExecutionContract  evaluationExecutionContract `json:"execution_contract"`
			}{name, struct {
				Binding struct {
					Node string `json:"node"`
					Role string `json:"role"`
				} `json:"binding"`
				Template json.RawMessage `json:"template"`
			}{struct {
				Node string `json:"node"`
				Role string `json:"role"`
			}{nodeName, role}, rawJSON(template)}, nodeName, nodeAddr, name, state.address("template", "condition", name), role, propositionAddr, resultContract, executionContract}
			state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termEvaluation, Kind: termConditionBinding, OrderingDependencies: ordering, RefreshDependencies: dedupe(append([]string{nodeAddr}, ordering...)), Payload: state.payload(payload)})
		}
	}
	state.addDiagnostics(findings)
}
