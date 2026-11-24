package sdl_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type replacedEnvelopeInstance struct{ sdl.InstantiatedScenario }

func (replacedEnvelopeInstance) Document() map[string]any { panic("foreign scenario method invoked") }

func TestEnvelopeMembershipUsesNativeInstantiatedOwner(t *testing.T) {
	raw, err := os.ReadFile("../../../contracts/fixtures/realization-envelope/realization-envelope-v1/valid/generic.json")
	if err != nil {
		t.Fatal(err)
	}
	var envelope binding.RealizationEnvelopeV1
	if err = json.Unmarshal(raw, &envelope); err != nil {
		t.Fatal(err)
	}
	source, err := sdl.Parse([]byte("name: sample\nnodes: {host: {type: compute}}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	findings, err := sdl.EnvelopeMembershipDiagnostics(instance, envelope)
	if err != nil || len(findings) != 0 {
		t.Fatalf("generic native member findings=%v err=%v", findings, err)
	}
	for _, input := range []sdl.InstantiatedScenario{nil, replacedEnvelopeInstance{instance}} {
		if _, err := sdl.EnvelopeMembershipDiagnostics(input, envelope); err == nil {
			t.Fatal("foreign instance admitted")
		}
	}
	if _, err := sdl.EnvelopeMembershipDiagnostics(instance, binding.RealizationEnvelopeV1{}); err == nil {
		t.Fatal("invalid envelope admitted")
	}
}

type envelopeModelReference struct {
	Name        string                        `json:"name"`
	Source      string                        `json:"source"`
	Envelope    binding.RealizationEnvelopeV1 `json:"envelope"`
	Diagnostics []envelopeDiagnosticReference `json:"diagnostics"`
}
type envelopeDiagnosticReference struct {
	Code    string `json:"code"`
	Address string `json:"address"`
	Message string `json:"message"`
}

func TestEnvelopeMembershipFollowsNativeModelFieldNames(t *testing.T) {
	raw, err := os.ReadFile("testdata/envelope-model-names.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []envelopeModelReference
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) { checkEnvelopeModelReference(t, test) })
	}
}
func checkEnvelopeModelReference(t *testing.T, test envelopeModelReference) {
	t.Helper()
	source, err := sdl.Parse([]byte(test.Source), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	actual, err := sdl.EnvelopeMembershipDiagnostics(instance, test.Envelope)
	if err != nil {
		t.Fatal(err)
	}
	if len(actual) != len(test.Diagnostics) {
		t.Fatalf("native model alias diagnostics=%v expected=%v", actual, test.Diagnostics)
	}
	for i, expected := range test.Diagnostics {
		if actual[i].Code != expected.Code || actual[i].Address != expected.Address || actual[i].Message != expected.Message {
			t.Fatalf("native alias mismatch=%v want=%v", actual[i], expected)
		}
	}
}
