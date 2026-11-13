package processor

import "encoding/json"

// Native wire projections for the existing mixed-control plan boundary.
type mixedDispositions struct {
	Duplicate  string `json:"duplicate"`
	Stale      string `json:"stale"`
	Revoked    string `json:"revoked"`
	Late       string `json:"late"`
	Concurrent string `json:"concurrent"`
	Conflict   string `json:"conflict"`
}

type mixedControllerState struct {
	Address                 string          `json:"address"`
	Name                    string          `json:"name"`
	Spec                    json.RawMessage `json:"spec"`
	OrderingDependencies    []string        `json:"ordering_dependencies"`
	RefreshDependencies     []string        `json:"refresh_dependencies"`
	StateID                 string          `json:"state_id"`
	ControllerRef           string          `json:"controller_ref"`
	ControllerAddress       string          `json:"controller_address"`
	AuthorityBasisRefs      []string        `json:"authority_basis_refs"`
	AuthorityBasisAddresses []string        `json:"authority_basis_addresses"`
	ScopeRefs               []string        `json:"scope_refs"`
	ScopeAddresses          []string        `json:"scope_addresses"`
	PolicyRevision          string          `json:"policy_revision"`
	ValidFromOrder          json.Number     `json:"valid_from_order"`
	ValidUntilOrder         json.Number     `json:"valid_until_order"`
	AuthorityStatus         string          `json:"authority_status"`
	EvidenceRefs            []string        `json:"evidence_refs"`
	EvidenceAddresses       []string        `json:"evidence_addresses"`
}

type mixedTransition struct {
	Address                     string          `json:"address"`
	Name                        string          `json:"name"`
	Spec                        json.RawMessage `json:"spec"`
	OrderingDependencies        []string        `json:"ordering_dependencies"`
	RefreshDependencies         []string        `json:"refresh_dependencies"`
	TransitionID                string          `json:"transition_id"`
	TransitionKind              string          `json:"transition_kind"`
	FromStateAddress            string          `json:"from_state_address"`
	ToStateAddress              string          `json:"to_state_address"`
	PolicyRevision              string          `json:"policy_revision"`
	ExpectedStateRevision       json.Number     `json:"expected_state_revision"`
	ResultingStateRevision      json.Number     `json:"resulting_state_revision"`
	EffectiveOrder              json.Number     `json:"effective_order"`
	ValidFromOrder              json.Number     `json:"valid_from_order"`
	ValidUntilOrder             json.Number     `json:"valid_until_order"`
	ProposalAddress             string          `json:"proposal_address"`
	ProposalRevision            *json.Number    `json:"proposal_revision"`
	EvidenceRefs                []string        `json:"evidence_refs"`
	EvidenceAddresses           []string        `json:"evidence_addresses"`
	CompletionEvidenceRefs      []string        `json:"completion_evidence_refs"`
	CompletionEvidenceAddresses []string        `json:"completion_evidence_addresses"`
}

type mixedPermission struct {
	Address                     string          `json:"address"`
	Name                        string          `json:"name"`
	Spec                        json.RawMessage `json:"spec"`
	OrderingDependencies        []string        `json:"ordering_dependencies"`
	RefreshDependencies         []string        `json:"refresh_dependencies"`
	TransitionID                string          `json:"transition_id"`
	TransitionKind              string          `json:"transition_kind"`
	FromStateAddress            string          `json:"from_state_address"`
	ToStateAddress              string          `json:"to_state_address"`
	ValidFromOrder              json.Number     `json:"valid_from_order"`
	ValidUntilOrder             json.Number     `json:"valid_until_order"`
	TargetKinds                 []string        `json:"target_kinds"`
	EvidenceRefs                []string        `json:"evidence_refs"`
	EvidenceAddresses           []string        `json:"evidence_addresses"`
	CompletionEvidenceRefs      []string        `json:"completion_evidence_refs"`
	CompletionEvidenceAddresses []string        `json:"completion_evidence_addresses"`
}

type mixedScriptStep struct {
	Address                    string          `json:"address"`
	Name                       string          `json:"name"`
	Spec                       json.RawMessage `json:"spec"`
	OrderingDependencies       []string        `json:"ordering_dependencies"`
	RefreshDependencies        []string        `json:"refresh_dependencies"`
	StepID                     string          `json:"step_id"`
	Position                   json.Number     `json:"position"`
	PermittedTransitionAddress string          `json:"permitted_transition_address"`
	ExpectedStateRevision      *json.Number    `json:"expected_state_revision"`
	ValidFromOrder             *json.Number    `json:"valid_from_order"`
	ValidUntilOrder            *json.Number    `json:"valid_until_order"`
	TargetKind                 string          `json:"target_kind"`
	TargetStepAddress          string          `json:"target_step_address"`
}

type mixedPolicy struct {
	Address              string            `json:"address"`
	Name                 string            `json:"name"`
	Spec                 json.RawMessage   `json:"spec"`
	OrderingDependencies []string          `json:"ordering_dependencies"`
	RefreshDependencies  []string          `json:"refresh_dependencies"`
	Semantics            string            `json:"semantics"`
	Form                 string            `json:"form"`
	ParticipantAddress   string            `json:"participant_address"`
	PolicyRevision       string            `json:"policy_revision"`
	OrderStrategy        string            `json:"order_strategy"`
	InitialStateAddress  string            `json:"initial_state_address"`
	PermittedTransitions []mixedPermission `json:"permitted_transitions"`
	ScriptSteps          []mixedScriptStep `json:"script_steps"`
}
