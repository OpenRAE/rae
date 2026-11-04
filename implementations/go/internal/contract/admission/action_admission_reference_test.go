package admission

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestActionAdmissionOwnerFieldsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var reference struct {
		Cases []struct {
			Name     string
			Changes  map[string]json.RawMessage
			Admitted bool
		}
	}
	readFullReferenceJSON(t, "testdata/action-admission-verdicts.json", &reference)
	if len(reference.Cases) != 37 {
		t.Fatal("independent action admission inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			_, context := flowContextFixture(t, e)
			request := context.snapshot.ActionAdmissions["action-admission.1"]
			applyActionOwnerChanges(t, &request, c.Changes)
			_, err := e.flowAction(request)
			if (err == nil) != c.Admitted {
				t.Fatalf("action admission differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

func applyActionOwnerChanges(t *testing.T, request *FlowActionRequest, changes map[string]json.RawMessage) {
	t.Helper()
	for name, value := range changes {
		field := reflect.ValueOf(request).Elem().FieldByName(name)
		if !field.IsValid() {
			t.Fatal("unknown action owner field")
		}
		if err := json.Unmarshal(value, field.Addr().Interface()); err != nil {
			t.Fatal(err)
		}
	}
}
