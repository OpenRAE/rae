package admission

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type fragmentVector struct {
	Profile  FragmentProfile `json:"profile"`
	Name     string          `json:"name"`
	Document json.RawMessage `json:"document"`
	Valid    bool            `json:"valid"`
}

func exactDocument(t *testing.T, data []byte) any {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var document any
	if err := decoder.Decode(&document); err != nil {
		t.Fatalf("Decode() error = %v", err)
	}
	return document
}

func TestFragmentsMatchTheReferenceModels(t *testing.T) {
	data, err := os.ReadFile("testdata/fragment-vectors.json")
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	var recording struct {
		Cases []fragmentVector `json:"cases"`
	}
	decodeJSON(t, data, &recording)
	v := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	recorded := map[FragmentProfile]bool{}
	for _, c := range recording.Cases {
		recorded[c.Profile] = true
		t.Run(string(c.Profile)+"/"+c.Name, func(t *testing.T) {
			got, err := AdmitFragment(v, c.Profile, exactDocument(t, c.Document), limits)
			if (err == nil) != c.Valid {
				t.Fatalf("AdmitFragment() error = %v, want admitted=%t", err, c.Valid)
			}
			if err == nil && got.Profile() != c.Profile {
				t.Errorf("Profile() = %q, want %q", got.Profile(), c.Profile)
			}
		})
	}
	for profile := range fragmentChecks() {
		if !recorded[profile] {
			t.Errorf("profile %s has no reference vector", profile)
		}
	}
}

func TestFragmentsAreCopies(t *testing.T) {
	v := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 16}
	document := map[string]any{"budget_state_ref": "b", "resource_kind": "accelerator", "unit": "accelerator_milliseconds", "meter_profile_ref": "m", "reserved": json.Number("1000000000000000000")}
	admitted, err := AdmitFragment(v, ParticipantResourceMeasurement, document, limits)
	if err != nil {
		t.Fatalf("AdmitFragment() error = %v", err)
	}
	document["unit"] = "changed"
	first, ok := admitted.Document().(map[string]any)
	if !ok {
		t.Fatalf("Document() = %T, want an object", admitted.Document())
	}
	first["unit"] = "changed"
	want := map[string]any{"budget_state_ref": "b", "resource_kind": "accelerator", "unit": "accelerator_milliseconds", "meter_profile_ref": "m", "reserved": json.Number("1000000000000000000")}
	if diff := cmp.Diff(want, admitted.Document()); diff != "" {
		t.Errorf("Document() mismatch (-want +got):\n%s", diff)
	}
	for _, root := range []any{"text", json.Number("3"), true, nil, []any{json.Number("1"), "x"}} {
		value, err := AdmitFragment(v, RealizationValue, root, limits)
		if err != nil {
			t.Fatalf("AdmitFragment(%v) error = %v", root, err)
		}
		if diff := cmp.Diff(root, value.Document()); diff != "" {
			t.Errorf("Document() mismatch (-want +got):\n%s", diff)
		}
	}
}

func TestFragmentsRefuseUnboundedOrUnknownInput(t *testing.T) {
	v := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 64, MaxDepth: 3}
	cyclic := []any{nil}
	cyclic[0] = cyclic
	cases := []struct {
		name      string
		validator *Validator
		profile   FragmentProfile
		document  any
	}{
		{"nil validator", nil, RealizationValue, "x"},
		{"unknown profile", v, FragmentProfile("unknown"), map[string]any{}},
		{"scalar root", v, RealizationDesignation, "x"},
		{"unsupported carrier", v, RealizationValue, func() {}},
		{"cycle", v, RealizationValue, cyclic},
		{"byte limit", v, RealizationValue, strings.Repeat("x", 64)},
		{"depth limit", v, RealizationValue, []any{[]any{[]any{[]any{"x"}}}}},
		{"object depth limit", v, RealizationConcern, map[string]any{"section": "s", "authored_path": []any{[]any{[]any{"x"}}}, "concern_kind": "k", "payload_path": []any{}}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, err := AdmitFragment(c.validator, c.profile, c.document, limits); err == nil {
				t.Fatal("AdmitFragment() admitted the document")
			}
		})
	}
}

func TestScalarFragmentByteCeilingDoesNotOverflow(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	maximum := int(^uint(0) >> 1)
	if _, err := AdmitFragment(owner, RealizationValue, "example", ingress.Limits{MaxBytes: maximum, MaxDepth: 8}); err != nil {
		t.Fatalf("wide byte ceiling overflowed: %v", err)
	}
	if _, err := AdmitFragment(owner, RealizationValue, "example", ingress.Limits{MaxBytes: 3, MaxDepth: 8}); err == nil {
		t.Fatal("encoded byte ceiling bypassed")
	}
}
