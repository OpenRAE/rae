package validation

import (
	"encoding/json"
	"fmt"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// These are recorded schema-and-model verdicts from the issue-1241 omission
// defects and issue-301 selector defects. Fragment admission checks each rule
// in every affected published phase without inventing surrounding owner data.
func TestPublishedSecurityRegressions(t *testing.T) {
	raw, err := os.ReadFile("testdata/security-regressions.json")
	if err != nil {
		t.Fatal(err)
	}
	var recorded struct {
		Cases []struct {
			ReferenceTest string          `json:"reference_test"`
			ContractID    string          `json:"contract_id"`
			Definition    string          `json:"definition"`
			Payload       json.RawMessage `json:"payload"`
			Valid         bool            `json:"valid"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &recorded); err != nil {
		t.Fatal(err)
	}
	if len(recorded.Cases) != 680 {
		t.Fatal("security regression inventory changed")
	}
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	for index, c := range recorded.Cases {
		t.Run(fmt.Sprintf("%s/%s/%s/%d", c.ReferenceTest, c.ContractID, c.Definition, index), func(t *testing.T) {
			_, err := v.DecodeObjectFragment(c.ContractID, "#/$defs/"+c.Definition, c.Payload, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64})
			if (err == nil) != c.Valid {
				t.Fatalf("schema admission=%v reference=%v error=%v", err == nil, c.Valid, err)
			}
		})
	}
}
