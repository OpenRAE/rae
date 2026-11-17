package sdl

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestEnvelopeWitnessUsesNativeSDLAdmission(t *testing.T) {
	raw, err := os.ReadFile("../contract/admission/testdata/backend/witness-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []nativeWitnessReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 6 {
		t.Fatal("reference")
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			checkNativeWitness(t, test)
		})
	}
}

type nativeWitnessReference struct {
	Name     string                        `json:"name"`
	Envelope binding.RealizationEnvelopeV1 `json:"envelope"`
	Valid    bool                          `json:"valid_witness"`
	Findings []struct {
		Code    string `json:"code"`
		Address string `json:"address"`
		Message string `json:"message"`
	} `json:"witness_diagnostics"`
}

func checkNativeWitness(t *testing.T, test nativeWitnessReference) {
	t.Helper()
	result, findings, err := EnvelopeWitness(test.Envelope)
	if err != nil {
		t.Fatal(err)
	}
	if (result != nil) != test.Valid || len(findings) != len(test.Findings) {
		t.Fatalf("witness=%v diagnostics=%+v", result, findings)
	}
	for i, want := range test.Findings {
		if findings[i].Code != want.Code || findings[i].Address != want.Address || findings[i].Message != want.Message {
			t.Fatalf("%+v want %+v", findings[i], want)
		}
	}
	if result != nil {
		membership, err := EnvelopeMembershipDiagnostics(result, test.Envelope)
		if err != nil || len(membership) > 0 {
			t.Fatal("witness is not a member", membership, err)
		}
	}
}
