package processor

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func TestCompiledProjectionConsumesOneAggregateBudget(t *testing.T) {
	payload := json.RawMessage(`{"value":"` + strings.Repeat("x", 750000) + `"}`)
	model := CompiledScenario{Name: "aggregate", Resources: []Resource{}}
	for i := range 12 {
		model.Resources = append(model.Resources, Resource{Address: "provision.node.host" + strings.Repeat("x", i), Kind: termNode, Payload: ResourcePayload{data: payload}})
	}
	raw, err := compiledProjection(model)
	if !errors.Is(err, value.ErrLimit) || raw != nil {
		t.Fatalf("oversized compiled aggregate published: bytes=%d err=%v", len(raw), err)
	}
}

type projectionMethodTrap struct{}

func (projectionMethodTrap) MarshalJSON() ([]byte, error) { panic("foreign method invoked") }

func TestCompiledProjectionNeverInvokesUnknownValueMethods(t *testing.T) {
	if err := value.ValidateProjected(map[string]any{"value": projectionMethodTrap{}}, value.Plan(), compiledProjectionValue); !errors.Is(err, value.ErrInput) {
		t.Fatalf("foreign carrier admitted: %v", err)
	}
}
