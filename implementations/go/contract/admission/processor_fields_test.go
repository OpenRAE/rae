package admission_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestSDLConstructionChecksSelectedValueKinds(t *testing.T) {
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		pointer, raw string
		valid        bool
	}{
		{"#/$defs/RuntimeConfiguration/properties/environment", `[{"name":"PUBLIC","value":"example"}]`, true},
		{"#/$defs/RuntimeConfiguration/properties/environment", `[{"name":"PUBLIC","extra":true}]`, false},
		{"#/$defs/Node/properties/type", `"compute"`, true},
		{"#/$defs/Node/properties/type", `"invalid"`, false},
		{"#", `[]`, false},
	} {
		err := owner.CheckSDLConstruction("sdl-authoring-input-v1", test.pointer, []byte(test.raw), ingress.Limits{MaxBytes: len(test.raw), MaxDepth: 32})
		if (err == nil) != test.valid {
			t.Fatalf("selected %s: valid=%v, err=%v", test.pointer, test.valid, err)
		}
	}
}
