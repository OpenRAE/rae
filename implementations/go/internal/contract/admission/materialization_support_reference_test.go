package admission

import (
	"encoding/json"
	"fmt"
	"strconv"
	"testing"
)

func TestPreparedRealizationSupportMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	count := 0
	for file := 1; file <= 2; file++ {
		var reference struct {
			Cases []struct {
				Requirement  json.RawMessage
				Declarations json.RawMessage
				Admitted     bool
			}
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/materialization-support-verdicts-%02d.json", file), &reference)
		for n, c := range reference.Cases {
			t.Run(strconv.Itoa(file)+"/"+strconv.Itoa(n), func(t *testing.T) {
				r := materializationInventory{execution: materializationExecution{manifest: map[string]any{"realization_support": decodeRuleObject(t, string(c.Declarations))}}}
				err := r.preparedSupport(decodeRuleObject(t, string(c.Requirement)))
				if (err == nil) != c.Admitted {
					t.Fatalf("prepared support differs from native admission (admitted=%v): %v", c.Admitted, err)
				}
			})
		}
		count += len(reference.Cases)
	}
	if count != 448 {
		t.Fatal("prepared support inventory changed", count)
	}
}
