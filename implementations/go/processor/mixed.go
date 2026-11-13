package processor

import (
	"cmp"
	"encoding/json"
	"maps"
	"math/big"
	"regexp"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type mixedSource struct {
	Semantics            string                     `json:"semantics"`
	Form                 string                     `json:"form"`
	ParticipantRef       string                     `json:"participant_ref"`
	PolicyRevision       string                     `json:"policy_revision"`
	OrderStrategy        string                     `json:"order_strategy"`
	InitialStateRef      string                     `json:"initial_state_ref"`
	Dispositions         mixedDispositions          `json:"dispositions"`
	ControllerStates     map[string]json.RawMessage `json:"controller_states"`
	Transitions          map[string]json.RawMessage `json:"transitions"`
	PermittedTransitions map[string]json.RawMessage `json:"permitted_transitions"`
	ScriptSteps          []json.RawMessage          `json:"script_steps"`
}
type mixedCompilation struct {
	participant, revision, order, initial, semantics string
	dispositions                                     *mixedDispositions
	states                                           []mixedControllerState
	transitions                                      []mixedTransition
	policy                                           *mixedPolicy
	dependencies                                     []string
	diagnostics                                      []diagnostic.Diagnostic
}

func (state *compilerState) mixedAddress(spec, kind, id string) string {
	return state.address(termParticipant, termBehaviorSpecification, spec, kind, id)
}
func (state *compilerState) compileMixedControllerStates(spec string, source mixedSource, participant string) ([]mixedControllerState, []string) {
	result := []mixedControllerState{}
	dependencies := []string{}
	for _, id := range slices.Sorted(maps.Keys(source.ControllerStates)) {
		raw := source.ControllerStates[id]
		var input struct {
			ControllerRef      string      `json:"controller_ref"`
			AuthorityBasisRefs []string    `json:"authority_basis_refs"`
			ScopeRefs          []string    `json:"scope_refs"`
			PolicyRevision     string      `json:"policy_revision"`
			ValidFromOrder     json.Number `json:"valid_from_order"`
			ValidUntilOrder    json.Number `json:"valid_until_order"`
			AuthorityStatus    string      `json:"authority_status"`
			EvidenceRefs       []string    `json:"evidence_refs"`
		}
		if err := json.Unmarshal(raw, &input); err != nil {
			state.err = invalidCompiled()
			return nil, nil
		}
		controller := participant
		if input.ControllerRef != termSelf {
			controller = state.address(termParticipant, "behavior", input.ControllerRef)
		}
		authority := state.runtimeAddressesFor(input.AuthorityBasisRefs, "authority-anchor")
		scope := state.runtimeAddressesFor(input.ScopeRefs, "authority-scope")
		evidence := state.runtimeAddresses(input.EvidenceRefs)
		refs := []string{controller}
		refs = append(refs, authority...)
		refs = append(refs, scope...)
		refs = append(refs, evidence...)
		refs = dedupe(refs)
		result = append(result, mixedControllerState{Address: state.mixedAddress(spec, "controller-state", id), Name: id, Spec: raw, OrderingDependencies: []string{}, RefreshDependencies: refs, StateID: id, ControllerRef: input.ControllerRef, ControllerAddress: controller, AuthorityBasisRefs: nonNilStrings(input.AuthorityBasisRefs), AuthorityBasisAddresses: authority, ScopeRefs: nonNilStrings(input.ScopeRefs), ScopeAddresses: scope, PolicyRevision: input.PolicyRevision, ValidFromOrder: input.ValidFromOrder, ValidUntilOrder: input.ValidUntilOrder, AuthorityStatus: input.AuthorityStatus, EvidenceRefs: nonNilStrings(input.EvidenceRefs), EvidenceAddresses: evidence})
		dependencies = append(dependencies, refs...)
	}
	return result, dedupe(dependencies)
}

type mixedTransitionSource struct {
	TransitionKind         string       `json:"transition_kind"`
	FromStateRef           string       `json:"from_state_ref"`
	ToStateRef             string       `json:"to_state_ref"`
	PolicyRevision         string       `json:"policy_revision"`
	ExpectedStateRevision  json.Number  `json:"expected_state_revision"`
	ResultingStateRevision json.Number  `json:"resulting_state_revision"`
	EffectiveOrder         json.Number  `json:"effective_order"`
	ValidFromOrder         json.Number  `json:"valid_from_order"`
	ValidUntilOrder        json.Number  `json:"valid_until_order"`
	ProposalRef            *string      `json:"proposal_ref"`
	ProposalRevision       *json.Number `json:"proposal_revision"`
	TargetKinds            []string     `json:"target_kinds"`
	EvidenceRefs           []string     `json:"evidence_refs"`
	CompletionEvidenceRefs []string     `json:"completion_evidence_refs"`
}

func integerOrder(input json.Number) *big.Int {
	value, ok := new(big.Int).SetString(string(input), 10)
	if !ok {
		return new(big.Int)
	}
	return value
}
func (state *compilerState) compileMixedTransitions(spec string, source mixedSource) ([]mixedTransition, []string) {
	ids := slices.Sorted(maps.Keys(source.Transitions))
	inputs := map[string]mixedTransitionSource{}
	for _, id := range ids {
		var input mixedTransitionSource
		if err := json.Unmarshal(source.Transitions[id], &input); err != nil {
			state.err = invalidCompiled()
			return nil, nil
		}
		inputs[id] = input
	}
	slices.SortStableFunc(ids, func(left, right string) int {
		return integerOrder(inputs[left].EffectiveOrder).Cmp(integerOrder(inputs[right].EffectiveOrder))
	})
	result := []mixedTransition{}
	dependencies := []string{}
	for _, id := range ids {
		input := inputs[id]
		from, to := state.mixedAddress(spec, "controller-state", input.FromStateRef), state.mixedAddress(spec, "controller-state", input.ToStateRef)
		proposal := ""
		refs := []string{from, to}
		if input.ProposalRef != nil {
			proposal = state.mixedAddress(spec, "control-transition", *input.ProposalRef)
			refs = append(refs, proposal)
		}
		evidence := state.runtimeAddresses(input.EvidenceRefs)
		completion := state.runtimeAddresses(input.CompletionEvidenceRefs)
		refs = append(refs, evidence...)
		refs = append(refs, completion...)
		refs = dedupe(refs)
		result = append(result, mixedTransition{Address: state.mixedAddress(spec, "control-transition", id), Name: id, Spec: source.Transitions[id], OrderingDependencies: []string{}, RefreshDependencies: refs, TransitionID: id, TransitionKind: input.TransitionKind, FromStateAddress: from, ToStateAddress: to, PolicyRevision: input.PolicyRevision, ExpectedStateRevision: input.ExpectedStateRevision, ResultingStateRevision: input.ResultingStateRevision, EffectiveOrder: input.EffectiveOrder, ValidFromOrder: input.ValidFromOrder, ValidUntilOrder: input.ValidUntilOrder, ProposalAddress: proposal, ProposalRevision: input.ProposalRevision, EvidenceRefs: nonNilStrings(input.EvidenceRefs), EvidenceAddresses: evidence, CompletionEvidenceRefs: nonNilStrings(input.CompletionEvidenceRefs), CompletionEvidenceAddresses: completion})
		dependencies = append(dependencies, refs...)
	}
	return result, dedupe(dependencies)
}

func (state *compilerState) compileMixedPermissions(spec string, source mixedSource) []mixedPermission {
	mixedKindTargets := map[string][]string{
		termProposal: {}, "approval": {termProposal}, "denial": {termProposal}, "external-direction": {termAction, termControl, termProposal}, "intervention": {termAction, "attempt", termControl}, "handoff": {}, "override": {termControl, termDecision}, "cancellation": {"admitted-action", "attempt", termDecision, termProposal},
	}
	result := []mixedPermission{}
	for _, id := range slices.Sorted(maps.Keys(source.PermittedTransitions)) {
		raw := source.PermittedTransitions[id]
		var input mixedTransitionSource
		if err := json.Unmarshal(raw, &input); err != nil {
			state.err = invalidCompiled()
			return nil
		}
		from, to := state.mixedAddress(spec, "controller-state", input.FromStateRef), state.mixedAddress(spec, "controller-state", input.ToStateRef)
		evidence := state.runtimeAddresses(input.EvidenceRefs)
		completion := state.runtimeAddresses(input.CompletionEvidenceRefs)
		refs := []string{from, to}
		refs = append(refs, evidence...)
		refs = append(refs, completion...)
		targets := input.TargetKinds
		if targets == nil {
			targets = mixedKindTargets[input.TransitionKind]
		}
		result = append(result, mixedPermission{Address: state.mixedAddress(spec, "permitted-transition", id), Name: id, Spec: raw, OrderingDependencies: []string{}, RefreshDependencies: dedupe(refs), TransitionID: id, TransitionKind: input.TransitionKind, FromStateAddress: from, ToStateAddress: to, ValidFromOrder: input.ValidFromOrder, ValidUntilOrder: input.ValidUntilOrder, TargetKinds: sortedTerms(targets), EvidenceRefs: nonNilStrings(input.EvidenceRefs), EvidenceAddresses: evidence, CompletionEvidenceRefs: nonNilStrings(input.CompletionEvidenceRefs), CompletionEvidenceAddresses: completion})
	}
	return result
}
func (state *compilerState) compileMixedScript(spec string, source mixedSource) []mixedScriptStep {
	result := []mixedScriptStep{}
	for i, raw := range source.ScriptSteps {
		var input struct {
			StepID                 string       `json:"step_id"`
			PermittedTransitionRef string       `json:"permitted_transition_ref"`
			ExpectedStateRevision  *json.Number `json:"expected_state_revision"`
			ValidFromOrder         *json.Number `json:"valid_from_order"`
			ValidUntilOrder        *json.Number `json:"valid_until_order"`
			TargetKind             string       `json:"target_kind"`
			TargetStepRef          string       `json:"target_step_ref"`
		}
		if err := json.Unmarshal(raw, &input); err != nil {
			state.err = invalidCompiled()
			return nil
		}
		transition := state.mixedAddress(spec, "permitted-transition", input.PermittedTransitionRef)
		target := ""
		refs := []string{transition}
		if input.TargetStepRef != "" {
			target = state.mixedAddress(spec, "script-step", input.TargetStepRef)
			refs = append(refs, target)
		}
		result = append(result, mixedScriptStep{Address: state.mixedAddress(spec, "script-step", input.StepID), Name: input.StepID, Spec: raw, OrderingDependencies: []string{}, RefreshDependencies: dedupe(refs), StepID: input.StepID, Position: json.Number(strconv.Itoa(i + 1)), PermittedTransitionAddress: transition, ExpectedStateRevision: input.ExpectedStateRevision, ValidFromOrder: input.ValidFromOrder, ValidUntilOrder: input.ValidUntilOrder, TargetKind: input.TargetKind, TargetStepAddress: target})
	}
	return result
}

var controlRefPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/@-]*$`)

func (state *compilerState) compileMixed(spec string, raw json.RawMessage) mixedCompilation {
	result := mixedCompilation{states: []mixedControllerState{}, transitions: []mixedTransition{}, dependencies: []string{}, diagnostics: []diagnostic.Diagnostic{}}
	if len(raw) == 0 || string(raw) == termNull {
		return result
	}
	var source mixedSource
	if err := json.Unmarshal(raw, &source); err != nil {
		state.err = invalidCompiled()
		return result
	}
	result.participant = state.address(termParticipant, "behavior", source.ParticipantRef)
	result.revision = source.PolicyRevision
	result.order = source.OrderStrategy
	result.initial = state.mixedAddress(spec, "controller-state", source.InitialStateRef)
	result.dispositions = &source.Dispositions
	states, stateDependencies := state.compileMixedControllerStates(spec, source, result.participant)
	result.states = states
	result.dependencies = append([]string{result.participant}, stateDependencies...)
	if source.Semantics == "" {
		result.semantics = "fixed-coordinate-v1"
		transitions, dependencies := state.compileMixedTransitions(spec, source)
		result.transitions = transitions
		result.dependencies = dedupe(append(result.dependencies, dependencies...))
		return result
	}
	result.semantics = source.Semantics
	permissions := state.compileMixedPermissions(spec, source)
	steps := state.compileMixedScript(spec, source)
	for _, permission := range permissions {
		result.dependencies = append(result.dependencies, permission.Address)
	}
	for _, permission := range permissions {
		result.dependencies = append(result.dependencies, permission.RefreshDependencies...)
	}
	result.dependencies = dedupe(result.dependencies)
	policy := &mixedPolicy{Address: state.address(termParticipant, termBehaviorSpecification, spec, "mixed-control-policy"), Name: spec, Spec: raw, OrderingDependencies: []string{}, RefreshDependencies: result.dependencies, Semantics: source.Semantics, Form: source.Form, ParticipantAddress: result.participant, PolicyRevision: source.PolicyRevision, OrderStrategy: source.OrderStrategy, InitialStateAddress: result.initial, PermittedTransitions: permissions, ScriptSteps: steps}
	result.policy = policy
	result.diagnostics = append(result.diagnostics, state.mixedReferenceDiagnostics(spec, result)...)

	return result
}

type mixedReference struct{ label, address string }

func (state *compilerState) mixedReferenceDiagnostics(spec string, result mixedCompilation) []diagnostic.Diagnostic {
	policy := result.policy
	permissions, steps, states := policy.PermittedTransitions, policy.ScriptSteps, result.states
	findings := []diagnostic.Diagnostic{}
	refs := []mixedReference{{"policy", policy.Address}, {termParticipantBehavior, policy.ParticipantAddress}}
	for _, item := range permissions {
		refs = append(refs, mixedReference{"permitted-transition", item.Address})
	}
	for _, item := range steps {
		refs = append(refs, mixedReference{"script-step", item.Address})
	}
	for _, item := range states {
		refs = append(refs, mixedReference{"controller-state", item.Address}, mixedReference{"controller", item.ControllerAddress})
	}
	slices.SortFunc(refs, func(a, b mixedReference) int {
		if order := cmp.Compare(a.label, b.label); order != 0 {
			return order
		}
		return cmp.Compare(a.address, b.address)
	})
	refs = slices.Compact(refs)
	for _, ref := range refs {
		if len(ref.address) > 256 || !controlRefPattern.MatchString(ref.address) {
			findings = append(findings, compileDiagnostic("participant.mixed-control-ref-out-of-range", termParticipant, state.address(termParticipant, termBehaviorSpecification, spec), "Compiled rev1 mixed-control "+ref.label+" address does not fit an API-424 ControlRef (at most 256 characters, portable pattern); it is never truncated."))
		}
	}
	return findings
}
