package trial

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestDescriptorMatchingPreservesScalarKindsAndExactPointAuthority(t *testing.T) {
	for _, test := range []struct {
		name, kind, expected, actual string
		valid                        bool
	}{
		{"integer", "literal", "1", "1", true}, {"integer-number", "literal", "1", "1.0", false},
		{"number", "literal", "1.0", "1.0", true}, {"boolean", "literal", "true", "true", true},
		{"string", "literal", `"value"`, `"value"`, true}, {"null", "literal", "null", "null", true},
		{"reference", "reference", `"ref"`, `"ref"`, true}, {"malformed", "literal", "{", "1", false},
	} {
		t.Run(test.name, func(t *testing.T) {
			d := descriptor{Target: descriptorTarget{Point: "point"}, Value: selectionOutcome{Kind: "literal", Value: json.RawMessage(test.expected)}}
			s := selectionRecord{Point: "point", Outcome: selectionOutcome{Kind: test.kind, Value: json.RawMessage(test.actual), ReferenceID: "ref"}}
			if got := descriptorMatches(Request{}, d, s); got != test.valid {
				t.Fatal("scalar binding identity changed", got, test.valid)
			}
			s.Point = "foreign"
			if descriptorMatches(Request{}, d, s) {
				t.Fatal("foreign point matched descriptor")
			}
		})
	}
	if descriptorMatches(Request{}, descriptor{Target: descriptorTarget{Point: "point"}, Value: selectionOutcome{Kind: "secret-reference"}}, selectionRecord{Point: "point"}) {
		t.Fatal("secret reference matched scalar selection")
	}
	if descriptorMatches(Request{}, descriptor{Target: descriptorTarget{Point: "point"}, Value: selectionOutcome{Kind: "literal"}}, selectionRecord{Point: "point", Outcome: selectionOutcome{Kind: "member", MemberID: "missing"}}) {
		t.Fatal("unowned alternative family matched descriptor")
	}
}

func TestParticipantConfigurationWorkIsBoundedBeforeOwnerResolution(t *testing.T) {
	request := Request{Limits: DefaultLimits()}
	request.Limits.MaxBindingsPerEntry = 1
	items := []admittedDescriptor{}
	for _, address := range []string{"p1", "p2"} {
		wire := descriptor{Target: descriptorTarget{Plane: planeParticipant, Participant: address, Name: "implementation", Version: "1", ManifestVersion: "v1", Target: "setting"}, Value: selectionOutcome{Kind: "literal", Value: json.RawMessage(`"value"`)}}
		items = append(items, admittedDescriptor{wire: wire})
	}
	if _, err := entryConfigurations(t.Context(), request, compilationInputs{}, nil, items); err == nil {
		t.Fatal("participant count exceeded the entry work bound")
	}
	items[0].wire.Value.Value = json.RawMessage(`{`)
	if _, err := configurationOverrides(compilationInputs{}, items[:1]); err == nil {
		t.Fatal("malformed binding value entered a configuration")
	}
	if _, err := realizeEntryConfiguration(t.Context(), request, compilationInputs{}, nil, ParticipantManifestKey{}, nil); err == nil {
		t.Fatal("unresolved participant manifest admitted")
	}
	if _, _, err := entryConfigurationContext(t.Context(), request, nil, []byte(`{`)); err == nil {
		t.Fatal("malformed owner metadata admitted")
	}
	if _, _, err := entryConfigurationContext(t.Context(), request, nil, []byte(`{"configuration_registry":{"owner":{"validator_id":"v","validator_version":"1"},"targets":{"prompt":{"control_context":{}}}}}`)); err == nil {
		t.Fatal("control-context declaration admitted without a scenario owner factory")
	}
	collector := entryBindingCollector{seen: map[string]bool{}}
	item := admittedDescriptor{wire: descriptor{ID: "binding"}, raw: json.RawMessage(`{}`)}
	if err := collector.append(item); err != nil {
		t.Fatal(err)
	}
	if err := collector.append(item); err == nil {
		t.Fatal("duplicate selected binding admitted")
	}
	item.wire.ID = "another"
	item.raw = json.RawMessage(`{`)
	if err := collector.append(item); err == nil {
		t.Fatal("malformed selected binding admitted")
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := admittedDescriptors(Request{}, compilationInputs{owner: owner, spec: experimentSpec{Bindings: json.RawMessage(`[]`)}}); err == nil {
		t.Fatal("malformed descriptor set admitted")
	}
}
