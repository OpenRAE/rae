package sdl_test

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestDescriptorProfilesKeepFieldOwnedBindingsAndCopies(t *testing.T) {
	raw, err := os.ReadFile("testdata/descriptor-profiles.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []descriptorReferenceCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Host, func(t *testing.T) {
			checkDescriptorReference(t, test)
		})
	}
}

type descriptorReferenceCase struct {
	Host    string          `json:"host"`
	Source  json.RawMessage `json:"source"`
	Binding json.RawMessage `json:"binding"`
}

func checkDescriptorReference(t *testing.T, test descriptorReferenceCase) {
	t.Helper()
	source, err := sdl.Parse(test.Source, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	profiles, err := sdl.DescriptorProfiles(source)
	if err != nil || len(profiles) != 1 {
		t.Fatalf("profiles=%d err=%v", len(profiles), err)
	}
	got := descriptorJSON(t, profiles[0])
	if !equalDescriptorJSON(t, got, test.Binding) {
		t.Fatalf("field-owned descriptor changed: got=%s want=%s", got, test.Binding)
	}
	value, _ := profiles[0].Value.Value()
	value[0] = 'x'
	copied, err := sdl.DescriptorProfiles(source)
	if err != nil || len(copied) != 1 {
		t.Fatalf("copied profiles=%d err=%v", len(copied), err)
	}
	if !equalDescriptorJSON(t, descriptorJSON(t, copied[0]), test.Binding) {
		t.Fatal("descriptor projection shared mutable bytes")
	}
}

func equalDescriptorJSON(t *testing.T, left, right []byte) bool {
	t.Helper()
	var a, b any
	if err := json.Unmarshal(left, &a); err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(right, &b); err != nil {
		t.Fatal(err)
	}
	return bytes.Equal(descriptorJSON(t, a), descriptorJSON(t, b))
}

func descriptorJSON(t *testing.T, input any) []byte {
	t.Helper()
	raw, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
