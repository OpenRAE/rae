package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestFlowSinkConjoinsCapabilityAndExactHistory(t *testing.T) {
	e := boundTestOwner(t)
	raw, c := flowContextFixture(t, e)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	capability := c.snapshot.CapabilityResolutions["capability-resolution.1"]
	capability.Disposition = "deny"
	c.snapshot.CapabilityResolutions[capability.Reference] = capability
	if _, err := e.Validate("participant-flow-control-relation-v1", raw, limits, c); err == nil {
		t.Fatal("permitted denied capability")
	}
	v, err := ingress.Parse(raw, limits, ingress.Object)
	if err != nil {
		t.Fatal(err)
	}
	object(array(at(v, "sink_decisions"))[0])["final_disposition"] = "deny"
	if _, err = e.Validate("participant-flow-control-relation-v1", controlJSON(t, v), limits, c); err != nil {
		t.Fatal(err)
	}
	c.snapshot.HistoryResolutions[0].Heads = []string{"stale-head"}
	if _, err = e.Validate("participant-flow-control-relation-v1", controlJSON(t, v), limits, c); err == nil {
		t.Fatal("accepted stale sink history")
	}
}

func TestFlowActionAdmissionChecksManifestExposureAndExecution(t *testing.T) {
	e := boundTestOwner(t)
	for _, name := range []string{"participant", "compiled-address", "selection", "visible", "disclosed", "evidence", "generation", "resource"} {
		t.Run(name, func(t *testing.T) {
			_, c := flowContextFixture(t, e)
			request := c.snapshot.ActionAdmissions["action-admission.1"]
			flowActionMutation(&request, name)
			if _, err := e.flowAction(request); err == nil {
				t.Fatal("accepted inconsistent action admission")
			}
		})
	}
	_, c := flowContextFixture(t, e)
	request := c.snapshot.ActionAdmissions["action-admission.1"]
	generation := json.Number("0")
	request.ExecutionScopeRef, request.ExecutionGeneration, request.TargetAddresses = "scope", &generation, []string{"target"}
	request.ResourceRequirements = []FlowResourceRequirement{{BudgetStateRef: "budget", Unit: "actions", MeterProfileRef: "meter", ResourceKind: json.RawMessage(`"action_rate"`), Reserved: jsonZero}}
	if _, err := e.flowAction(request); err != nil {
		t.Fatal(err)
	}
}

func flowActionMutation(r *FlowActionRequest, name string) {
	switch name {
	case "participant":
		r.ParticipantAddress = "other"
	case "compiled-address":
		r.ActionContractAddress = "uncompiled"
	case "selection":
		r.Selection.ActionContractAddress = "participant.action-contract.other"
	case "visible":
		r.VisibleRefs = []string{"private-visible"}
	case "disclosed":
		r.DisclosedRefs = []string{"private-disclosed"}
	case "evidence":
		r.EvidenceRefs = []string{"private-evidence"}
	case "generation":
		generation := json.Number("0")
		r.ExecutionGeneration = &generation
	case "resource":
		r.ResourceRequirements = []FlowResourceRequirement{{BudgetStateRef: "budget", Unit: "tokens", MeterProfileRef: "meter", ResourceKind: json.RawMessage(`"action_rate"`), Reserved: jsonZero}}
	}
}
