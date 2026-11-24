package admission

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestTimeManagementModesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	count := 0
	for shard := 1; shard <= 7; shard++ {
		var reference struct {
			Cases []struct {
				Value    json.RawMessage `json:"value"`
				Admitted bool            `json:"admitted"`
			} `json:"cases"`
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/time-management-verdicts-%02d.json", shard), &reference)
		for _, c := range reference.Cases {
			count++
			t.Run(fmt.Sprintf("%04d", count), func(t *testing.T) {
				err := timeManagementModel(decodeRuleObject(t, string(c.Value)))
				if (err == nil) != c.Admitted {
					t.Fatalf("time-management claim differs from Python (admitted=%v): %v", c.Admitted, err)
				}
			})
		}
	}
	if count != 5632 {
		t.Fatal("independent time-management inventory changed")
	}
}
