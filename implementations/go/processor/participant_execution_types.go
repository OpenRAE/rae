package processor

import (
	"encoding/json"
)

// Typed projections for the existing participant execution plan boundary.
type participantExecutionBinding struct {
	ActionContractAddress                     string      `json:"action_contract_address"`
	TargetAddresses                           []string    `json:"target_addresses"`
	ParticipantImplementationRef              string      `json:"participant_implementation_ref"`
	MaxActionAttempts                         json.Number `json:"max_action_attempts"`
	MaxInFlight                               json.Number `json:"max_in_flight"`
	InteractionClasses                        []string    `json:"interaction_classes"`
	SharedStateRefs                           []string    `json:"shared_state_refs"`
	RelatedActionContractAddresses            []string    `json:"related_action_contract_addresses"`
	CommutativeSharedStateRefs                []string    `json:"commutative_shared_state_refs"`
	CommutativeRelatedActionContractAddresses []string    `json:"commutative_related_action_contract_addresses"`
	MergeRuleRefs                             []string    `json:"merge_rule_refs"`
	SharedStateMergeRules                     [][2]string `json:"shared_state_merge_rules"`
	RelatedActionMergeRules                   [][2]string `json:"related_action_merge_rules"`
}

type participantInvocationTool struct {
	ToolAffordanceAddress           string                       `json:"tool_affordance_address"`
	ToolAddress                     string                       `json:"tool_address"`
	ActionContractAddress           string                       `json:"action_contract_address"`
	ObservationBoundaryAddresses    []string                     `json:"observation_boundary_addresses"`
	ParticipantAddresses            []string                     `json:"participant_addresses"`
	TargetAddresses                 []string                     `json:"target_addresses"`
	SharedTimeBound                 bool                         `json:"shared_time_bound"`
	ObservationBoundaryEvidenceRefs []participantEvidencePair    `json:"observation_boundary_evidence_refs"`
	Interaction                     *participantExecutionBinding `json:"interaction"`
}

type participantAutonomous struct {
	Address                            string                        `json:"address"`
	Name                               string                        `json:"name"`
	Spec                               json.RawMessage               `json:"spec"`
	OrderingDependencies               []string                      `json:"ordering_dependencies"`
	RefreshDependencies                []string                      `json:"refresh_dependencies"`
	BehaviorSpecificationAddress       string                        `json:"behavior_specification_address"`
	ParticipantAddresses               []string                      `json:"participant_addresses"`
	ParticipantImplementationRef       string                        `json:"participant_implementation_ref"`
	ClockAddress                       string                        `json:"clock_address"`
	ProgressionPolicyAddress           string                        `json:"progression_policy_address"`
	TemporalConstraintAddresses        []string                      `json:"temporal_constraint_addresses"`
	ActionContractAddresses            []string                      `json:"action_contract_addresses"`
	TargetAddresses                    []string                      `json:"target_addresses"`
	ExecutionBindings                  []participantExecutionBinding `json:"execution_bindings"`
	ObservationBoundaryAddress         string                        `json:"observation_boundary_address"`
	ObservationBoundaryEvidenceRefs    []string                      `json:"observation_boundary_evidence_refs"`
	SelectionStrategy                  string                        `json:"selection_strategy"`
	MaxActionAttempts                  json.Number                   `json:"max_action_attempts"`
	MaxInFlight                        json.Number                   `json:"max_in_flight"`
	FailurePolicy                      string                        `json:"failure_policy"`
	EvaluationAuthorityMode            string                        `json:"evaluation_authority_mode"`
	ObjectiveRefs                      []string                      `json:"objective_refs"`
	ProofProducerRefs                  []string                      `json:"proof_producer_refs"`
	ScoreAuthorityRefs                 []string                      `json:"score_authority_refs"`
	ReceiptAuthorityRefs               []string                      `json:"receipt_authority_refs"`
	Profile                            string                        `json:"profile"`
	WorkWindowAddresses                []string                      `json:"work_window_addresses"`
	PauseWindowAddresses               []string                      `json:"pause_window_addresses"`
	StochasticControlRef               string                        `json:"stochastic_control_ref"`
	TimingMinimumTicks                 json.Number                   `json:"timing_minimum_ticks"`
	TimingMaximumTicks                 json.Number                   `json:"timing_maximum_ticks"`
	OutsideWindowDisposition           string                        `json:"outside_window_disposition"`
	EmptyEligibleDisposition           string                        `json:"empty_eligible_disposition"`
	ActionCandidateIDs                 []string                      `json:"action_candidate_ids"`
	ActionCandidateWeights             []json.Number                 `json:"action_candidate_weights"`
	ActionCandidateDependencies        [][]string                    `json:"action_candidate_dependencies"`
	ActionCandidateRetryFailureClasses [][]string                    `json:"action_candidate_retry_failure_classes"`
	ActionCandidateMaxRetries          []json.Number                 `json:"action_candidate_max_retries"`
	ActionCandidateCooldownTicks       []json.Number                 `json:"action_candidate_cooldown_ticks"`
	MaxOccurrences                     json.Number                   `json:"max_occurrences"`
	MaxBurstSize                       json.Number                   `json:"max_burst_size"`
	ResourceOwners                     []participantResourceOwner    `json:"resource_owners"`
	ResourceDemands                    []participantResourceDemand   `json:"resource_demands"`
	ResourceFairness                   participantResourceFairness   `json:"resource_fairness"`
	TemporalBindings                   []participantTemporalBinding  `json:"temporal_bindings"`
	InvocationToolBindings             []participantInvocationTool   `json:"invocation_tool_bindings"`
}

type participantResourceOwner struct {
	OwnerID string `json:"owner_id"`
	Kind    string `json:"kind"`
	Address string `json:"address"`
}

type participantResourceDemand struct {
	BudgetID        string                  `json:"budget_id"`
	OwnerID         string                  `json:"owner_id"`
	OwnerKind       string                  `json:"owner_kind"`
	OwnerAddress    string                  `json:"owner_address"`
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
	Provenance      string                  `json:"provenance"`
}

type participantResourceFairness struct {
	Policy               string      `json:"policy"`
	PriorityClass        string      `json:"priority_class"`
	Weight               json.Number `json:"weight"`
	Protected            bool        `json:"protected"`
	Borrowing            string      `json:"borrowing"`
	Reclaim              string      `json:"reclaim"`
	MaxQueueTicks        json.Number `json:"max_queue_ticks"`
	StarvationBoundTicks json.Number `json:"starvation_bound_ticks"`
}

type participantEvidencePair struct {
	Address string
	Refs    []string
}

func (pair participantEvidencePair) MarshalJSON() ([]byte, error) {
	return json.Marshal([]any{pair.Address, pair.Refs})
}
