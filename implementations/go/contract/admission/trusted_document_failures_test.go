package admission

import (
	"fmt"
	"reflect"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// Owner documents arrive independently of the candidate. Exercise corrupt
// owner records after proving the unchanged candidate and owner are accepted.
func TestTrustedControlDocumentsRejectCorruption(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	for _, fixture := range []struct{ version, name string }{{"v1", "teaching-inject"}, {"v2", "dependency-chain"}} {
		t.Run(fixture.version, func(t *testing.T) {
			factory := func() (any, any, []reflect.Value) {
				v, c := controlResolutionFixture(t, e, fixture.version, fixture.name)
				return v, c, []reflect.Value{reflect.ValueOf(&c.snapshot).Elem()}
			}
			checkTrustedDocumentCorruption(t, e, "participant-control-evaluation-"+fixture.version, factory)
		})
	}
}

func TestTrustedCompositionDocumentsRejectCorruption(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	for _, name := range []string{"simultaneous", "alternative", "staged"} {
		t.Run(name, func(t *testing.T) {
			factory := func() (any, any, []reflect.Value) {
				raw, c := mixedContextFixture(t, e, name)
				return decodeRuleObject(t, string(raw)), c, []reflect.Value{reflect.ValueOf(&c.snapshot).Elem()}
			}
			checkTrustedDocumentCorruption(t, e, "mixed-participant-composition-profile-v1", factory)
		})
	}
}

func TestTrustedFlowDocumentsRejectCorruption(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	factory := func() (any, any, []reflect.Value) {
		raw, c := flowContextFixture(t, e)
		return decodeRuleObject(t, string(raw)), c, []reflect.Value{reflect.ValueOf(&c.snapshot).Elem()}
	}
	checkTrustedDocumentCorruption(t, e, "participant-flow-control-relation-v1", factory)
}

func TestTrustedMaterializationDocumentsRejectCorruption(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var fixtures []materializationExecutionFixture
	readFullReferenceJSON(t, "testdata/materialization-execution.json", &fixtures)
	for _, fixture := range fixtures {
		t.Run(fixture.Name, func(t *testing.T) {
			factory := func() (any, any, []reflect.Value) {
				c := materializationExecutionTestFixture(t, e, fixture)
				v := map[string]any{"contract_id": "backend-materialization-attestation-v1", "sdl": fixture.Submission}
				return v, c, []reflect.Value{reflect.ValueOf(&c.snapshot).Elem(), reflect.ValueOf(&c.original).Elem(), reflect.ValueOf(&c.current).Elem()}
			}
			checkTrustedDocumentCorruption(t, e, "backend-materialization-attestation-v1", factory)
		})
	}
}

type trustedDocumentFault struct {
	name string
	set  func([]reflect.Value, []byte)
}

func checkTrustedDocumentCorruption(t *testing.T, e *Validator, id string, factory func() (any, any, []reflect.Value)) {
	t.Helper()
	value, context, owners := factory()
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	raw := controlJSON(t, value)
	if _, err := e.Validate(id, raw, limits, context); err != nil {
		t.Fatal("independent baseline owner:", err)
	}
	faults := trustedDocumentFaults(owners)
	if len(faults) == 0 {
		t.Fatal("missing trusted document faults")
	}
	for _, fault := range faults {
		for _, replacement := range []string{"{", "[]", "{}"} {
			t.Run(fault.name+"/"+replacement, func(t *testing.T) {
				_, changed, states := factory()
				fault.set(states, []byte(replacement))
				admitted, err := e.Validate(id, raw, limits, changed)
				if err == nil || admitted.ContractID() != "" {
					t.Fatal("corrupt trusted document yielded an admitted value:", err)
				}
			})
		}
	}
}

func trustedDocumentFaults(owners []reflect.Value) []trustedDocumentFault {
	var faults []trustedDocumentFault

	for ownerIndex, owner := range owners {
		faults = append(faults, trustedOwnerFieldFaults(ownerIndex, owner)...)
	}
	return faults
}

func trustedOwnerFieldFaults(ownerIndex int, owner reflect.Value) []trustedDocumentFault {
	var faults []trustedDocumentFault
	bytesType := reflect.TypeFor[[]byte]()
	valueType := reflect.TypeFor[validation.Value]()
	for fieldIndex := range owner.NumField() {
		field := owner.Field(fieldIndex)
		name := fmt.Sprintf("%d/%s", ownerIndex, owner.Type().Field(fieldIndex).Name)
		switch {
		case field.Type() == valueType && trustedValuePresent(field):
			faults = append(faults, trustedDocumentFault{name, func(states []reflect.Value, _ []byte) { states[ownerIndex].Field(fieldIndex).SetZero() }})
		case field.Type() == bytesType && field.Len() > 0:
			faults = append(faults, trustedDocumentFault{name, func(states []reflect.Value, raw []byte) { states[ownerIndex].Field(fieldIndex).SetBytes(raw) }})
		case field.Kind() == reflect.Slice && field.Type().Elem() == bytesType:
			for index := range field.Len() {
				faults = append(faults, trustedDocumentFault{fmt.Sprintf("%s/%d", name, index), func(states []reflect.Value, raw []byte) {
					states[ownerIndex].Field(fieldIndex).Index(index).SetBytes(raw)
				}})
			}
		case field.Kind() == reflect.Map && field.Type().Elem() == bytesType:
			for _, key := range field.MapKeys() {
				faults = append(faults, trustedDocumentFault{fmt.Sprintf("%s/%v", name, key.Interface()), func(states []reflect.Value, raw []byte) {
					states[ownerIndex].Field(fieldIndex).SetMapIndex(key, reflect.ValueOf(raw))
				}})
			}
		}
	}
	return faults
}

func trustedValuePresent(field reflect.Value) bool {
	admitted, ok := reflect.TypeAssert[validation.Value](field)
	return ok && admitted.ContractID() != ""
}
