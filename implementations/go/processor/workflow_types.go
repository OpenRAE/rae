package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type workflowPredicateSource struct {
	Assertions []string `json:"assertions"`
	Objectives []string `json:"objectives"`
	Steps      []struct {
		Step        string       `json:"step"`
		Outcomes    []string     `json:"outcomes"`
		MinAttempts *json.Number `json:"min_attempts"`
	} `json:"steps"`
}
type workflowStepSource struct {
	Type                  string                   `json:"type"`
	ExecutionMode         string                   `json:"execution_mode"`
	Objective             string                   `json:"objective"`
	ProcedureRef          string                   `json:"procedure_ref"`
	ScaffoldRefs          []string                 `json:"scaffold_refs"`
	AllowedActionFamilies []string                 `json:"allowed_action_families"`
	ToolAffordanceRefs    []string                 `json:"tool_affordance_refs"`
	CapabilityRefs        []string                 `json:"capability_refs"`
	FactBindingRefs       []string                 `json:"fact_binding_refs"`
	Next                  string                   `json:"next"`
	OnSuccess             string                   `json:"on_success"`
	OnFailure             string                   `json:"on_failure"`
	OnExhausted           string                   `json:"on_exhausted"`
	When                  *workflowPredicateSource `json:"when"`
	Then                  string                   `json:"then"`
	Else                  string                   `json:"else"`
	Cases                 []struct {
		When workflowPredicateSource `json:"when"`
		Next string                  `json:"next"`
	} `json:"cases"`
	Default        string       `json:"default"`
	Branches       []string     `json:"branches"`
	Join           string       `json:"join"`
	Workflow       string       `json:"workflow"`
	CompensateWith string       `json:"compensate_with"`
	MaxAttempts    *json.Number `json:"max_attempts"`
}
type workflowStepState struct {
	StepType              string   `json:"step_type"`
	StateObservable       bool     `json:"state_observable"`
	ObservableOutcomes    []string `json:"observable_outcomes"`
	SupportsAttemptCounts bool     `json:"supports_attempt_counts"`
	FixedAttempts         *int     `json:"fixed_attempts"`
}
type workflowStatePredicate struct {
	StepName    string       `json:"step_name"`
	Outcomes    []string     `json:"outcomes"`
	MinAttempts *json.Number `json:"min_attempts"`
}
type workflowPredicate struct {
	AssertionAddresses  []string                 `json:"assertion_addresses"`
	ObjectiveAddresses  []string                 `json:"objective_addresses"`
	StepStatePredicates []workflowStatePredicate `json:"step_state_predicates"`
}
type workflowSwitchCase struct {
	CaseIndex int               `json:"case_index"`
	Predicate workflowPredicate `json:"predicate"`
	NextStep  string            `json:"next_step"`
}
type workflowRuntimeStep struct {
	Name                        string               `json:"name"`
	StepType                    string               `json:"step_type"`
	ExecutionMode               string               `json:"execution_mode"`
	ObjectiveAddress            string               `json:"objective_address"`
	ProcedureRef                string               `json:"procedure_ref"`
	ScaffoldRefs                []string             `json:"scaffold_refs"`
	AllowedActionFamilies       []string             `json:"allowed_action_families"`
	ToolAffordanceRefs          []string             `json:"tool_affordance_refs"`
	CapabilityRefs              []string             `json:"capability_refs"`
	FactBindingRefs             []string             `json:"fact_binding_refs"`
	Predicate                   *workflowPredicate   `json:"predicate"`
	NextStep                    string               `json:"next_step"`
	OnSuccess                   string               `json:"on_success"`
	OnFailure                   string               `json:"on_failure"`
	OnExhausted                 string               `json:"on_exhausted"`
	ThenStep                    string               `json:"then_step"`
	ElseStep                    string               `json:"else_step"`
	SwitchCases                 []workflowSwitchCase `json:"switch_cases"`
	DefaultStep                 string               `json:"default_step"`
	Branches                    []string             `json:"branches"`
	JoinStep                    string               `json:"join_step"`
	OwningParallelStep          string               `json:"owning_parallel_step"`
	CalledWorkflowAddress       string               `json:"called_workflow_address"`
	CompensationWorkflowAddress string               `json:"compensation_workflow_address"`
	MaxAttempts                 *json.Number         `json:"max_attempts"`
	StateContract               workflowStepState    `json:"state_contract"`
}
type workflowResult struct {
	StateSchemaVersion string                       `json:"state_schema_version"`
	ObservableSteps    map[string]workflowStepState `json:"observable_steps"`
}
type workflowExecution struct {
	StateSchemaVersion        string                       `json:"state_schema_version"`
	StartStep                 string                       `json:"start_step"`
	TimeoutSeconds            *json.Number                 `json:"timeout_seconds"`
	Steps                     map[string]workflowStepState `json:"steps"`
	StepTypes                 map[string]string            `json:"step_types"`
	ControlEdges              map[string][]string          `json:"control_edges"`
	JoinOwners                map[string]string            `json:"join_owners"`
	CallSteps                 map[string]string            `json:"call_steps"`
	CompensationMode          string                       `json:"compensation_mode"`
	CompensationTriggers      []string                     `json:"compensation_triggers"`
	CompensationTargets       map[string]string            `json:"compensation_targets"`
	CompensationOrdering      string                       `json:"compensation_ordering"`
	CompensationFailurePolicy string                       `json:"compensation_failure_policy"`
	ObservableSteps           []string                     `json:"observable_steps"`
}
type workflowPayload struct {
	Name                           string                         `json:"name"`
	Spec                           json.RawMessage                `json:"spec"`
	StartStep                      string                         `json:"start_step"`
	ReferencedObjectiveAddresses   []string                       `json:"referenced_objective_addresses"`
	ControlSteps                   map[string]workflowRuntimeStep `json:"control_steps"`
	ControlEdges                   map[string][]string            `json:"control_edges"`
	JoinOwners                     map[string]string              `json:"join_owners"`
	StepAssertionAddresses         map[string][]string            `json:"step_assertion_addresses"`
	StepPredicateAddresses         map[string][]string            `json:"step_predicate_addresses"`
	RequiredFeatures               []string                       `json:"required_features"`
	RequiredStatePredicateFeatures []string                       `json:"required_state_predicate_features"`
	ResultContract                 workflowResult                 `json:"result_contract"`
	ExecutionContract              workflowExecution              `json:"execution_contract"`
	StateSchemaVersion             string                         `json:"state_schema_version"`
}
type workflowCompilation struct {
	payload                                                         workflowPayload
	objectiveAddresses, predicateAddresses, features, stateFeatures []string
	diagnostics                                                     []diagnostic.Diagnostic
}
