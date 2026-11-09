package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type sdlConstructorVector struct {
	Name     string            `json:"name"`
	Pointer  string            `json:"pointer"`
	Contract string            `json:"contract"`
	Accepted bool              `json:"accepted"`
	Data     json.RawMessage   `json:"data"`
	Changes  []referenceChange `json:"changes"`
}

func sdlConstructorVectors(t *testing.T) []sdlConstructorVector {
	t.Helper()
	raw, err := os.ReadFile("testdata/sdl-constructors.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []sdlConstructorVector `json:"cases"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	return fixture.Cases
}

func TestSDLConstructorOracle(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range sdlConstructorVectors(t) {
		t.Run(c.Name, func(t *testing.T) { checkSDLConstructorVector(t, owner, c) })
	}
}

func checkSDLConstructorVector(t *testing.T, owner *Validator, c sdlConstructorVector) {
	t.Helper()
	if len(c.Changes) > 0 {
		root := decodeRuleObject(t, string(c.Data))
		for _, change := range c.Changes {
			applyReferenceChange(t, root, change)
		}
		c.Data = controlJSON(t, root)
	}
	contract := c.Contract
	if contract == "" {
		contract = "sdl-authoring-input-v1"
	}
	limits := ingress.Limits{MaxBytes: len(c.Data)}
	var err error
	if contract == "instantiated-scenario-v1" {
		err = owner.CheckModelFragment(contract, c.Pointer, c.Data, limits)
	} else {
		err = owner.CheckSDLConstruction(contract, c.Pointer, c.Data, limits)
	}
	if (err == nil) != c.Accepted {
		t.Fatalf("accepted=%v want %v: %v", err == nil, c.Accepted, err)
	}
}
