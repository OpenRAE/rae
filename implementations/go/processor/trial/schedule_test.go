package trial

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestSchedulingAndReadmissionUseCompleteSealedAuthority(t *testing.T) {
	ref := referenceCompilations(t)[0]
	request := compilerRequest(t, ref.Request)
	result, err := Compile(request)
	if err != nil || result.Plan == nil {
		t.Fatal(result.Diagnostics, err)
	}
	schedule, err := PlanBatchSchedule(*result.Plan)
	if err != nil {
		t.Fatal(err)
	}
	if schedule.AdmittedParallelismCeiling != 1 || len(schedule.Entries) != 2 || schedule.Entries[0].DispatchOrdinal != 0 || schedule.Entries[1].DispatchOrdinal != 1 {
		t.Fatal("invalid serial schedule", schedule)
	}
	if _, checkErr := Readmit(context.Background(), *result.Plan, request); checkErr != nil {
		t.Fatal(checkErr)
	}
	var changed map[string]any
	if json.Unmarshal(ref.Plan, &changed) != nil {
		t.Fatal("bad reference")
	}
	changed["plan_id"] = "foreign-plan"
	raw, err := json.Marshal(changed)
	if err != nil {
		t.Fatal(err)
	}
	if json.Unmarshal(raw, result.Plan) != nil {
		t.Fatal("bad candidate")
	}
	if _, err := Readmit(context.Background(), *result.Plan, request); err == nil {
		t.Fatal("accepted changed candidate")
	}
}

func TestRealizationAssignmentKeyRequiresAValidCoordinate(t *testing.T) {
	owner, err := trialOwner()
	if err != nil {
		t.Fatal(err)
	}
	for _, raw := range []string{`null`, `{"replicate_id":""}`, `{"replicate_id":" "}`, `{"condition_id":"a","replicate_id":"replicate-000001","extra":true}`} {
		var document any
		if decode([]byte(raw), &document) != nil {
			t.Fatal("bad coordinate test")
		}
		fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, document, trialIngress())
		if err != nil {
			t.Fatal(err)
		}
		if key, err := RealizationAssignmentKey(fragment); err == nil {
			t.Fatal("invalid coordinate admitted", raw, key)
		}
	}
}
