package governance

import (
	"testing"
)

func TestYAMLReferenceProfiles(t *testing.T) {
	cases := readReference[[]struct {
		Source string `json:"Source"`
		Repr   string `json:"Repr"`
		Error  bool   `json:"Error"`
	}](t, "yaml-reference")
	for _, tc := range cases {
		t.Run(tc.Source, func(t *testing.T) {
			value, err := yamlValue([]byte(tc.Source), false)
			if (err != nil) != tc.Error {
				t.Fatalf("constructor error=%v, want refusal=%t", err, tc.Error)
			}
			if err == nil {
				if got := pythonRepr(value); got != tc.Repr {
					t.Errorf("repr=%s, want %s", got, tc.Repr)
				}
			}
		})
	}
}
