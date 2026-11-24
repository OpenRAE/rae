package processor

import "encoding/json"

// Private records for the published participant resource projection.
type participantSpecification struct {
	Name                               string                    `json:"name"`
	Spec                               json.RawMessage           `json:"spec"`
	ControlContext                     []controlContextSelection `json:"control_context,omitempty"`
	SpecName                           string                    `json:"spec_name"`
	SemanticVersion                    string                    `json:"semantic_version"`
	LifecycleState                     string                    `json:"lifecycle_state"`
	ParticipantAddresses               []string                  `json:"participant_addresses"`
	ParticipantRoleRefs                []string                  `json:"participant_role_refs"`
	ActionContractAddresses            []string                  `json:"action_contract_addresses"`
	ObservationBoundaryAddresses       []string                  `json:"observation_boundary_addresses"`
	OutcomeInterpretationRuleAddresses []string                  `json:"outcome_interpretation_rule_addresses"`
	AuthorityScopeRefs                 []string                  `json:"authority_scope_refs"`
	AuthorityScopeAddresses            []string                  `json:"authority_scope_addresses"`
	BehaviorMode                       string                    `json:"behavior_mode"`
	AutonomousExecution                *participantAutonomous    `json:"autonomous_execution"`
	MixedControlParticipantAddress     string                    `json:"mixed_control_participant_address"`
	MixedControlPolicyRevision         string                    `json:"mixed_control_policy_revision"`
	MixedControlOrderStrategy          string                    `json:"mixed_control_order_strategy"`
	MixedControlInitialStateAddress    string                    `json:"mixed_control_initial_state_address"`
	MixedControlDispositions           *mixedDispositions        `json:"mixed_control_dispositions"`
	ControllerStates                   []mixedControllerState    `json:"controller_states"`
	ControlTransitions                 []mixedTransition         `json:"control_transitions"`
	MixedControlSemantics              string                    `json:"mixed_control_semantics"`
	MixedControlPolicy                 *mixedPolicy              `json:"mixed_control_policy"`
	RealizationProfileRef              string                    `json:"realization_profile_ref"`
	BackendFeatureSupportRefs          []string                  `json:"backend_feature_support_refs"`
	EvidenceContractRefs               []string                  `json:"evidence_contract_refs"`
	ToolAffordanceAddresses            []string                  `json:"tool_affordance_addresses"`
	ParticipantInjectDeliveryAddresses []string                  `json:"participant_inject_delivery_addresses"`
	ExtensionPolicy                    string                    `json:"extension_policy"`
	ExtensionKeys                      []string                  `json:"extension_keys"`
}
type participantDelivery struct {
	Name                           string                      `json:"name"`
	Spec                           json.RawMessage             `json:"spec"`
	BindingID                      string                      `json:"binding_id"`
	BehaviorSpecificationAddress   string                      `json:"behavior_specification_address"`
	ParticipantAddress             string                      `json:"participant_address"`
	InjectAddress                  string                      `json:"inject_address"`
	EventAddress                   string                      `json:"event_address"`
	ScriptAddress                  string                      `json:"script_address"`
	StoryAddress                   string                      `json:"story_address"`
	SourceItemRef                  string                      `json:"source_item_ref"`
	SourceItemAddress              string                      `json:"source_item_address"`
	ResultItemRef                  string                      `json:"result_item_ref"`
	ResultItemAddress              string                      `json:"result_item_address"`
	ObservationBoundaryAddress     string                      `json:"observation_boundary_address"`
	DeliveryKind                   string                      `json:"delivery_kind"`
	PolicyRef                      string                      `json:"policy_ref"`
	PolicyRevision                 string                      `json:"policy_revision"`
	ExposurePolicyRef              string                      `json:"exposure_policy_ref"`
	AudienceScopeRef               string                      `json:"audience_scope_ref"`
	VisibilityBasisRef             string                      `json:"visibility_basis_ref"`
	DisclosureBasisRef             string                      `json:"disclosure_basis_ref"`
	OrderBasis                     string                      `json:"order_basis"`
	TemporalConstraintAddresses    []string                    `json:"temporal_constraint_addresses"`
	EvidenceRequirementAddresses   []string                    `json:"evidence_requirement_addresses"`
	FailureDisposition             string                      `json:"failure_disposition"`
	ControlTransitionAddress       string                      `json:"control_transition_address"`
	ControllerAddress              string                      `json:"controller_address"`
	ControlAuthorityScopeRefs      []string                    `json:"control_authority_scope_refs"`
	ControlAuthorityScopeAddresses []string                    `json:"control_authority_scope_addresses"`
	ControlEffectiveOrder          *json.Number                `json:"control_effective_order"`
	ControlValidFromOrder          *json.Number                `json:"control_valid_from_order"`
	ControlValidUntilOrder         *json.Number                `json:"control_valid_until_order"`
	ControlEvidenceRefs            []string                    `json:"control_evidence_refs"`
	ControlEvidenceAddresses       []string                    `json:"control_evidence_addresses"`
	Control                        *participantDeliveryControl `json:"control"`
}
type participantDeliveryControl struct {
	Semantics                  string   `json:"semantics"`
	PolicyRevision             string   `json:"policy_revision"`
	PermittedTransitionAddress string   `json:"permitted_transition_address"`
	ControllerAddress          string   `json:"controller_address"`
	AuthorityScopeRefs         []string `json:"authority_scope_refs"`
	AuthorityScopeAddresses    []string `json:"authority_scope_addresses"`
	EvidenceRefs               []string `json:"evidence_refs"`
	EvidenceAddresses          []string `json:"evidence_addresses"`
}
