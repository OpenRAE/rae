package admission

import (
	"encoding/json"
	"fmt"
	"reflect"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestResolvedControlOwnerChangesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var reference struct {
		Cases []struct {
			Field    string          `json:"field"`
			Key      *string         `json:"key"`
			Path     []string        `json:"path"`
			Value    json.RawMessage `json:"value"`
			Admitted bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/control-owner-verdicts.json", &reference)
	if len(reference.Cases) != 719 {
		t.Fatal("missing independent control owner cases")
	}
	v, baseline := controlResolutionFixture(t, e, "v1", "teaching-inject")
	if err := e.controlResolvedContext(validation.Invocation{Key: validation.Key{ContractID: "participant-control-evaluation-v1"}, Instance: v, Context: baseline}); err != nil {
		t.Fatal("baseline owner:", err)
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%03d/%s", index, c.Field), func(t *testing.T) {
			_, context := controlResolutionFixture(t, e, "v1", "teaching-inject")
			alterRecordedControlOwner(t, &context.snapshot, c.Field, c.Key, referenceChange{Path: c.Path, Value: c.Value})
			err := e.controlResolvedContext(validation.Invocation{Key: validation.Key{ContractID: "participant-control-evaluation-v1"}, Instance: v, Context: context})
			if (err == nil) != c.Admitted {
				t.Fatalf("resolved owner differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

func alterRecordedControlOwner(t *testing.T, snapshot *ControlResolutionSnapshot, fieldName string, key *string, change referenceChange) {
	t.Helper()
	field := reflect.ValueOf(snapshot).Elem().FieldByName(fieldName)
	if !field.IsValid() {
		t.Fatal("unknown recorded owner field")
	}
	var raw []byte
	if key == nil {
		raw = field.Bytes()
	} else {
		raw = field.MapIndex(reflect.ValueOf(*key)).Bytes()
	}
	owner := decodeRuleObject(t, string(raw))
	applyReferenceChange(t, owner, change)
	changed := controlJSON(t, owner)
	if key == nil {
		field.SetBytes(changed)
	} else {
		field.SetMapIndex(reflect.ValueOf(*key), reflect.ValueOf(changed))
	}
}
