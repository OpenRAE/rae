package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestEnvelopeWitnessProjectionMatchesPythonReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/backend/witness-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []witnessReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 6 {
		t.Fatal("reference")
	}
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			checkWitnessReference(t, test, owner)
		})
	}
}

type witnessReference struct {
	Name     string                        `json:"name"`
	Envelope binding.RealizationEnvelopeV1 `json:"envelope"`
	Payload  any                           `json:"payload"`
	Findings []struct {
		Code    string `json:"code"`
		Address string `json:"address"`
		Message string `json:"message"`
	} `json:"build_diagnostics"`
}

func checkWitnessReference(t *testing.T, test witnessReference, owner *Validator) {
	t.Helper()
	payload, findings, err := EnvelopeWitnessProjection(owner, test.Envelope)
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != len(test.Findings) {
		t.Fatal(findings, test.Findings)
	}
	for i, want := range test.Findings {
		if findings[i].Code != want.Code || findings[i].Address != want.Address || findings[i].Message != want.Message {
			t.Fatalf("%+v want %+v", findings[i], want)
		}
	}
	if len(findings) == 0 {
		actual, marshalErr := json.Marshal(payload.Document())
		if marshalErr != nil {
			t.Fatal(marshalErr)
		}
		var decoded any
		if json.Unmarshal(actual, &decoded) != nil {
			t.Fatal("payload")
		}
		if diff := cmp.Diff(test.Payload, decoded); diff != "" {
			t.Fatal(diff)
		}
	}
}
