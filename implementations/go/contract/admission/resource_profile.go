package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
)

type resourceContextProjection struct {
	Capabilities resourceCapabilitiesProjection `json:"capabilities"`
}

type resourceCapabilitiesProjection struct {
	Runtime resourceRuntimeProjection `json:"participant_runtime"`
}

type resourceRuntimeProjection struct {
	Budgets resourceBudgetsProjection `json:"resource_budgets"`
}

type resourceBudgetsProjection struct {
	Context json.RawMessage `json:"domain_profile_context"`
}

// resourceProfileContext returns the original bytes of the resource-budget
// profile context. The bytes keep the member order of each profile schema.
func resourceProfileContext(data []byte) ([]byte, error) {
	var wire resourceContextProjection
	if err := json.Unmarshal(data, &wire); err != nil {
		return nil, invalid()
	}
	return wire.Capabilities.Runtime.Budgets.Context, nil
}

func (e *Validator) checkResourceProfiles(root any, data []byte) error {
	caps := at(root, "capabilities", "participant_runtime", "resource_budgets")
	if caps == nil {
		return nil
	}
	context, err := resourceProfileContext(data)
	if err != nil {
		return err
	}
	for _, pool := range array(at(caps, "configured_pools")) {
		if object(at(pool, "resource_kind")) == nil {
			continue
		}
		admitted := false
		for _, reset := range stringsOf(at(caps, "supported_reset_modes")) {
			if e.resourceMeasureSupported(pool, reset, context) {
				admitted = true
				break
			}
		}
		if !admitted {
			return invalid()
		}
	}
	return nil
}

type measureSemantics struct {
	Contract string `json:"contract"`
	Value    string `json:"value"`
	Effect   string `json:"effect"`
}

func resourceMeasureSemantics() any {
	digest, err := jsonDigest(measureSemantics{Contract: "participant-resource-measure/v1", Value: "unit, existing accounting mode, exact meter and existing reset mode", Effect: "existing integer budget/pool reservation, measured settlement, generation and evidence enforcement"})
	if err != nil {
		return nil
	}
	return map[string]any{termAuthority: "https://openrae.org/profiles", "contract_id": "participant-resource-measure", termRevision: "1", "digest": digest}
}

const termDomainProfileBindingV1 = "domain-profile-binding/v1"

type measureOwner struct {
	OwningContractID string `json:"owning_contract_id"`
	CanonicalAddress string `json:"canonical_address"`
	ConceptFamily    string `json:"concept_family"`
	LifecyclePhase   string `json:"lifecycle_phase"`
	Context          string `json:"context"`
	Use              string `json:"use"`
}

type measureValue struct {
	Unit            string `json:"unit"`
	AccountingMode  string `json:"accounting_mode"`
	MeterProfileRef string `json:"meter_profile_ref"`
	Reset           string `json:"reset"`
}

type measureProvenance struct {
	Basis     string `json:"basis"`
	SourceRef string `json:"source_ref"`
}

// measureBinding is the binding of one pool's exact quantity semantics.
type measureBinding struct {
	SchemaVersion string            `json:"schema_version"`
	BindingID     string            `json:"binding_id"`
	Coordinate    any               `json:"coordinate"`
	Owner         measureOwner      `json:"owner"`
	Value         measureValue      `json:"value"`
	Provenance    measureProvenance `json:"provenance"`
}

// resourceMeasurePolicy requires execution and typed-report support.
func resourceMeasurePolicy() (binding.DomainProfileAdmissionPolicyV1, error) {
	var policy binding.DomainProfileAdmissionPolicyV1
	err := json.Unmarshal([]byte(`{"schema_version":"domain-profile-admission-policy/v1","required_operations":["execution","typed-report"]}`), &policy)
	return policy, err
}

// resourceMeasureSupported admits the exact quantity semantics of one pool
// through the profile owner. A coordinate alone never authorizes use.
func (e *Validator) resourceMeasureSupported(pool any, reset string, context []byte) bool {
	if len(context) == 0 || string(context) == "null" {
		return false
	}
	kind := at(pool, "resource_kind")
	coordinate := profile.DomainCoordinate{Namespace: stringAt(kind, "namespace"), Authority: stringAt(kind, termAuthority), ProfileID: stringAt(kind, termProfileID), Revision: stringAt(kind, termRevision), DefinitionDigest: stringAt(kind, "definition_digest")}
	resolution, err := e.owners.ResolveDomainProfile(coordinate, context)
	if err != nil || resolution.Outcome != profile.Resolved || !resourceSemanticContract(resolution.Definition) {
		return false
	}
	measure, err := json.Marshal(measureBinding{
		SchemaVersion: termDomainProfileBindingV1, BindingID: "measure", Coordinate: kind,
		Owner:      measureOwner{OwningContractID: "participant-resource-budget-policy-v1", CanonicalAddress: "#/quantity", ConceptFamily: "resource-accounting", LifecyclePhase: termExecution, Context: "participant-resource-measure", Use: "constraint"},
		Value:      measureValue{Unit: stringAt(pool, "unit"), AccountingMode: stringAt(pool, "accounting_mode"), MeterProfileRef: stringAt(pool, "meter_profile_ref"), Reset: reset},
		Provenance: measureProvenance{Basis: "author-supplied", SourceRef: "urn:openrae:resource-budget"},
	})
	if err != nil {
		return false
	}
	var request binding.DomainProfileBindingV1
	policy, err := resourceMeasurePolicy()
	if err != nil || json.Unmarshal(measure, &request) != nil {
		return false
	}
	report, err := e.owners.AdmitDomainBindings([]binding.DomainProfileBindingV1{request}, context, policy)
	return err == nil && report.Admitted()
}

func resourceSemanticContract(definition *binding.DomainProfileDefinitionV1) bool {
	data, err := json.Marshal(definition)
	if err != nil {
		return false
	}
	var wire struct {
		SemanticContract map[string]any `json:"semantic_contract"`
	}
	return json.Unmarshal(data, &wire) == nil && equal(wire.SemanticContract, resourceMeasureSemantics())
}
