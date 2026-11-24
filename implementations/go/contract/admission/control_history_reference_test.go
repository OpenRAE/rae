package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type controlHistoryReference struct {
	Records []json.RawMessage `json:"records"`
	Context struct {
		Declarations []ControlDeclaration `json:"declarations"`
		Policies     []json.RawMessage    `json:"policies"`
		Targets      []ControlTarget      `json:"known_targets"`
		Available    []struct {
			ControlTarget

			AvailableAt json.Number `json:"available_at"`
		} `json:"available_targets"`
	} `json:"context"`
	Admitted bool `json:"admitted"`
}

func TestControlHistoryPoliciesAndLifecyclesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	count := 0
	for shard := 1; shard <= 3; shard++ {
		var reference struct {
			Cases []controlHistoryReference `json:"cases"`
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/control-history-verdicts-%02d.json", shard), &reference)
		for _, c := range reference.Cases {
			count++
			t.Run(fmt.Sprintf("%03d", count), func(t *testing.T) {
				checkControlHistoryReference(t, e, c)
			})
		}
	}
	if count != 98 {
		t.Fatal("missing control history reference inventory")
	}
}

func checkControlHistoryReference(t *testing.T, e *Validator, c controlHistoryReference) {
	t.Helper()
	context := controlHistoryTestContext{records: flowRawList(c.Records), policies: flowRawList(c.Context.Policies), declarations: c.Context.Declarations, targets: c.Context.Targets}
	for _, target := range c.Context.Available {
		context.available = append(context.available, AvailableControlTarget{Target: target.ControlTarget, AvailableAt: target.AvailableAt})
	}
	if len(c.Records) == 0 {
		index := controlOccurrenceIndex{declarations: map[string]any{}, targets: map[string]any{}}
		err := index.authorities(c.Context.Declarations, c.Context.Targets)
		if (err == nil) != c.Admitted {
			t.Fatalf("empty-history authority differs from Python (admitted=%v): %v", c.Admitted, err)
		}
		return
	}
	raw := c.Records[len(c.Records)-1]
	candidate := decodeRuleObject(t, string(raw))
	id := controlLineage(candidate)
	admitted, err := e.Validate(id, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, context)
	if (err == nil) != c.Admitted {
		t.Fatalf("control history differs from Python (admitted=%v): %v", c.Admitted, err)
	}
	if err != nil && admitted.ContractID() != "" {
		t.Fatal("invalid history returned admitted value")
	}
}
