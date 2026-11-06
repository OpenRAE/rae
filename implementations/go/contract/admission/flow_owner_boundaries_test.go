package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestActionOwnerAdaptersRefuseMalformedTypedCarriers(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	for _, name := range []string{"manifest", "implementation-selection", "result", "temporal-context", "temporal-evidence", "argument-shape", "argument-identity", "argument-disclosures", "argument-name", "argument-json", "argument-depth", "argument-null", "argument-map", "argument-null-list", "argument-nested-list", "resource-json", "resource-number", "resource-profile", "duplicate-resource"} {
		t.Run(name, func(t *testing.T) {
			_, c := flowContextFixture(t, e)
			r := c.snapshot.ActionAdmissions["action-admission.1"]
			alterMalformedActionOwner(&r, name)
			if _, err := e.flowAction(r); err == nil {
				t.Fatal("malformed typed action owner admitted")
			}
		})
	}
}

func alterMalformedActionOwner(r *FlowActionRequest, name string) {
	switch name {
	case "manifest":
		r.Manifest = validation.Value{}
	case "implementation-selection":
		r.ImplementationSelection = []byte("{")
	case "result":
		r.ActionResult = []byte("{")
	case "temporal-context":
		r.TemporalContexts = [][]byte{[]byte("{")}
	case "temporal-evidence":
		r.TemporalEvidence = [][]byte{[]byte("{")}
	case "argument-shape":
		r.Selection.ArgumentShapeRef = ""
	case "argument-identity":
		r.Selection.ProposalRef = ""
	case "argument-disclosures":
		r.Selection.NormalizationDisclosureRefs = []string{"same", "same"}
	case "argument-name":
		r.Selection.Arguments = map[string]json.RawMessage{"": json.RawMessage(`1`)}
	case "argument-json":
		r.Selection.Arguments = map[string]json.RawMessage{"arg": json.RawMessage(`{`)}
	case "argument-depth":
		r.Selection.Arguments = map[string]json.RawMessage{"arg": json.RawMessage(`[[[[[1]]]]]`)}
	case "argument-null":
		r.Selection.Arguments = map[string]json.RawMessage{"arg": json.RawMessage(`null`)}
	case "argument-map":
		r.Selection.Arguments = map[string]json.RawMessage{"arg": json.RawMessage(`{}`)}
	case "argument-null-list":
		r.Selection.Arguments = map[string]json.RawMessage{"arg": json.RawMessage(`[null]`)}
	case "argument-nested-list":
		r.Selection.Arguments = map[string]json.RawMessage{"arg": json.RawMessage(`[[1]]`)}
	case "resource-json", "resource-number", "resource-profile", "duplicate-resource":
		resource := FlowResourceRequirement{BudgetStateRef: "budget", Unit: "actions", MeterProfileRef: "meter", Reserved: jsonZero, ResourceKind: json.RawMessage(`"action_rate"`)}
		if name == "resource-json" {
			resource.ResourceKind = json.RawMessage(`{`)
		}
		if name == "resource-number" {
			resource.Reserved = json.Number("invalid")
		}
		if name == "resource-profile" {
			resource.ResourceKind = json.RawMessage(`{}`)
		}
		r.ResourceRequirements = []FlowResourceRequirement{resource}
		if name == "duplicate-resource" {
			r.ResourceRequirements = append(r.ResourceRequirements, resource)
		}
	}
}
