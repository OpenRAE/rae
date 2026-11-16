package trial

import (
	"bytes"
	"encoding/json"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

var trialOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Immutable schema owner, with no request data.

type coordinate struct {
	ConditionID *string `json:"condition_id"`
	BlockID     *string `json:"block_id"`
	ReplicateID *string `json:"replicate_id"`
}

func (c coordinate) projection() any {
	return struct {
		ConditionID *string `json:"condition_id,omitempty"`
		BlockID     *string `json:"block_id,omitempty"`
		ReplicateID *string `json:"replicate_id,omitempty"`
	}{c.ConditionID, c.BlockID, c.ReplicateID}
}

type reference struct {
	Kind    string     `json:"ref_kind"`
	ID      string     `json:"ref_id"`
	Version *string    `json:"ref_version"`
	Digest  *string    `json:"ref_digest"`
	Path    *string    `json:"ref_path"`
	Subject *reference `json:"subject_ref"`
}
type inputReferences struct {
	Authoring  reference   `json:"authoring_input_ref"`
	Task       reference   `json:"task_ref"`
	TaskDigest string      `json:"task_digest"`
	Family     reference   `json:"scenario_family_ref"`
	Bindings   *reference  `json:"binding_descriptor_set_ref"`
	Capture    []reference `json:"capture_spec_refs"`
	Study      *reference  `json:"study_ref"`
	Associated *reference  `json:"associated_artifact_set_ref"`
	Mixed      []reference `json:"mixed_composition_profile_refs"`
}
type selectionOutcome struct {
	Kind        string          `json:"kind"`
	Value       json.RawMessage `json:"value,omitempty"`
	MemberID    string          `json:"member_id,omitempty"`
	MemberIDs   []string        `json:"member_ids,omitempty"`
	ReferenceID string          `json:"reference_id,omitempty"`
}
type selectionPolicy struct {
	Kind     string                      `json:"kind"`
	ID       string                      `json:"policy_id"`
	Point    string                      `json:"point_ref"`
	Bound    int                         `json:"output_bound"`
	Refs     []string                    `json:"policy_refs"`
	Outcome  selectionOutcome            `json:"outcome"`
	Outcomes map[string]selectionOutcome `json:"outcomes"`
	Strata   map[string]struct {
		ID      string `json:"stratum_id"`
		Outcome string `json:"outcome_ref"`
		Count   int    `json:"output_count"`
	} `json:"strata"`
	Control        string   `json:"stochastic_control_ref"`
	DescriptorRefs []string `json:"binding_descriptor_refs"`
}
type randomStreamEntropy struct {
	Kind     string `json:"kind"`
	Encoding string `json:"encoding"`
	Value    string `json:"value"`
}

type stochasticControl struct {
	ID         string `json:"control_id"`
	Role       string `json:"role"`
	Executable *struct {
		Profile   reference           `json:"profile_ref"`
		Namespace string              `json:"namespace"`
		Entropy   randomStreamEntropy `json:"root_entropy"`
	} `json:"executable_binding"`
}
type runAllocation struct {
	Conditions   []string                   `json:"compared_conditions"`
	PerCondition int                        `json:"target_runs_per_condition"`
	Assignments  map[string]json.RawMessage `json:"condition_assignments"`
}

type experimentSpec struct {
	ID              string          `json:"spec_id"`
	Version         string          `json:"spec_version"`
	Task            reference       `json:"task_ref"`
	Capture         []reference     `json:"capture_spec_refs"`
	Bindings        json.RawMessage `json:"binding_descriptors"`
	Factorial       json.RawMessage `json:"factorial_design"`
	ApparatusIntent json.RawMessage `json:"apparatus_intent"`
	RunPlan         struct {
		Count             int                        `json:"target_run_count"`
		Policies          map[string]selectionPolicy `json:"selection_policies"`
		Controls          []json.RawMessage          `json:"stochastic_controls"`
		Allocation        *runAllocation             `json:"allocation"`
		AllocationPolicy  json.RawMessage            `json:"allocation_policy"`
		ReplacementPolicy json.RawMessage            `json:"replacement_policy"`
		EvidenceRelations []json.RawMessage          `json:"evidence_requirement_relations"`
	} `json:"run_plan"`
}
type executionAuthority struct {
	Timeout        int             `json:"attempt_timeout_seconds"`
	OnTimeout      string          `json:"on_timeout"`
	OnCancellation string          `json:"on_cancellation"`
	Cleanup        json.RawMessage `json:"cleanup"`
}
type selectionRecord struct {
	Point     string           `json:"variation_point_id"`
	Policy    string           `json:"origin_policy_id"`
	Kind      string           `json:"origin_policy_kind"`
	Outcome   selectionOutcome `json:"outcome"`
	Treatment json.RawMessage  `json:"treatment,omitempty"`
}
type selectionRow struct {
	selections []selectionRecord
	draws      []json.RawMessage
}
type entryProvenance struct {
	PlanID   string `json:"plan_id"`
	EntryID  string `json:"plan_entry_id"`
	RunID    string `json:"run_id"`
	FamilyID string `json:"scenario_family_id"`
}
type executionControls struct {
	Timeout        int    `json:"attempt_timeout_seconds"`
	OnTimeout      string `json:"on_timeout"`
	OnCancellation string `json:"on_cancellation"`
	CleanupRef     string `json:"cleanup_plan_ref"`
}
type trialEntry struct {
	signature      string
	ID             string            `json:"plan_entry_id"`
	Coordinate     coordinate        `json:"coordinate"`
	RunID          string            `json:"run_id"`
	Selections     []selectionRecord `json:"selections"`
	Bindings       []json.RawMessage `json:"bindings"`
	Configurations []json.RawMessage `json:"participant_configurations,omitempty"`
	Draws          []json.RawMessage `json:"stochastic_draws"`
	Apparatus      json.RawMessage   `json:"apparatus"`
	Controls       executionControls `json:"execution_controls"`
	Provenance     entryProvenance   `json:"instantiation_provenance"`
	Digest         string            `json:"entry_digest,omitempty"`
}
type trialPlan struct {
	ID                string                     `json:"plan_id"`
	Digest            string                     `json:"plan_digest,omitempty"`
	Profiles          json.RawMessage            `json:"profiles"`
	Refs              json.RawMessage            `json:"input_refs"`
	Controls          map[string]json.RawMessage `json:"stochastic_controls"`
	Cleanup           map[string]json.RawMessage `json:"cleanup_plans"`
	Entries           map[string]trialEntry      `json:"entries"`
	ReplacementPolicy json.RawMessage            `json:"replacement_policy,omitempty"`
	ReplacementOrigin json.RawMessage            `json:"replacement_origin,omitempty"`
	Allocation        json.RawMessage            `json:"allocation,omitempty"`
	Admission         struct {
		Stage string `json:"admitted_at_stage"`
		Count int    `json:"entry_count"`
	} `json:"admission"`
	Isolation json.RawMessage `json:"isolation_proof,omitempty"`
}

func trialInvalid() error { return fault.New(fault.InvalidInput, "trial-input-invalid", nil) }
func decode(data []byte, target any) error {
	d := json.NewDecoder(bytes.NewReader(data))
	d.UseNumber()
	if d.Decode(target) != nil {
		return trialInvalid()
	}
	return nil
}
func encoded(input any) ([]byte, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, trialInvalid()
	}
	return raw, nil
}
func canonical(input any) ([]byte, error) {
	raw, err := encoded(input)
	if err != nil {
		return nil, err
	}
	return canonjson.JCS(raw)
}
func hash(input any) (string, error) {
	raw, err := canonical(input)
	if err != nil {
		return "", err
	}
	return digest.SHA256(raw), nil
}
func identity(kind string, projection any, mixed bool) (string, error) {
	domain := "raes-trial-compiler-identity-v1"
	if mixed {
		domain = "raes-trial-compiler-mixed-composition-identity-v1"
	}
	material := struct {
		Domain     string `json:"domain"`
		Kind       string `json:"kind"`
		Projection any    `json:"projection"`
	}{domain, kind, projection}
	d, err := hash(material)
	if err != nil {
		return "", err
	}
	return kind + "-" + strings.TrimPrefix(d, "sha256:"), nil
}
func fragmentDocument(owner *admission.Validator, input any) (admission.Fragment, error) { //nolint:ireturn // Native admission owns the opaque fragment.
	raw, err := encoded(input)
	if err != nil {
		return nil, err
	}
	var value any
	if decode(raw, &value) != nil {
		return nil, trialInvalid()
	}
	return admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64})
}
func isNull(raw json.RawMessage) bool { return len(raw) == 0 || bytes.Equal(raw, []byte("null")) }
func text(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}
