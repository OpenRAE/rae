package processor

import "encoding/json"

// These records decode admitted policy leaves at the compiler input boundary.
// They retain exact integers and do not perform a second SDL admission.
type participantActionCandidate struct {
	ActionRef               string      `json:"action_ref"`
	Weight                  json.Number `json:"weight"`
	DependsOn               []string    `json:"depends_on"`
	RetryableFailureClasses []string    `json:"retryable_failure_classes"`
	MaxRetries              json.Number `json:"max_retries"`
	CooldownTicks           json.Number `json:"cooldown_ticks"`
}
type participantBudgetOwner struct {
	Kind string `json:"kind"`
	Ref  string `json:"ref"`
}
type participantBudgetDimension struct {
	OwnerRef        string                  `json:"owner_ref"`
	PoolRef         string                  `json:"pool_ref"`
	ResourceKind    participantResourceKind `json:"resource_kind"`
	Unit            string                  `json:"unit"`
	AccountingMode  string                  `json:"accounting_mode"`
	MeterProfileRef string                  `json:"meter_profile_ref"`
	Limit           json.Number             `json:"limit"`
	Reservation     json.Number             `json:"reservation"`
	Reset           string                  `json:"reset"`
	WindowTicks     *json.Number            `json:"window_ticks"`
	ParentBudgetRef *string                 `json:"parent_budget_ref"`
	EvidenceRefs    []string                `json:"evidence_refs"`
}
type participantBudget struct {
	Owners     map[string]participantBudgetOwner     `json:"owners"`
	Dimensions map[string]participantBudgetDimension `json:"dimensions"`
	Fairness   participantResourceFairness           `json:"fairness"`
}
type participantExecutionSource struct {
	Profile                      string                                `json:"profile"`
	ParticipantImplementationRef string                                `json:"participant_implementation_ref"`
	ClockRef                     string                                `json:"clock_ref"`
	ProgressionPolicyRef         string                                `json:"progression_policy_ref"`
	TemporalConstraintRefs       []string                              `json:"temporal_constraint_refs"`
	ActionOrder                  []string                              `json:"action_order"`
	ActionCandidates             map[string]participantActionCandidate `json:"action_candidates"`
	ObservationBoundaryRef       string                                `json:"observation_boundary_ref"`
	SelectionStrategy            string                                `json:"selection_strategy"`
	MaxActionAttempts            json.Number                           `json:"max_action_attempts"`
	MaxInFlight                  json.Number                           `json:"max_in_flight"`
	FailurePolicy                string                                `json:"failure_policy"`
	EvaluationAuthority          struct {
		Mode                 string   `json:"mode"`
		ObjectiveRefs        []string `json:"objective_refs"`
		ProofProducerRefs    []string `json:"proof_producer_refs"`
		ScoreAuthorityRefs   []string `json:"score_authority_refs"`
		ReceiptAuthorityRefs []string `json:"receipt_authority_refs"`
	} `json:"evaluation_authority"`
	WorkWindowRefs       []string `json:"work_window_refs"`
	PauseWindowRefs      []string `json:"pause_window_refs"`
	StochasticControlRef string   `json:"stochastic_control_ref"`
	Timing               *struct {
		MinimumTicks json.Number `json:"minimum_ticks"`
		MaximumTicks json.Number `json:"maximum_ticks"`
	} `json:"timing"`
	OutsideWindowDisposition string             `json:"outside_window_disposition"`
	EmptyEligibleDisposition string             `json:"empty_eligible_disposition"`
	MaxOccurrences           json.Number        `json:"max_occurrences"`
	MaxBurstSize             json.Number        `json:"max_burst_size"`
	ResourceBudget           *participantBudget `json:"resource_budget"`
}
