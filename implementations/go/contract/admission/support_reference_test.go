package admission

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestRealizationSupportMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Count int      `json:"case_count"`
		Files []string `json:"case_files"`
	}
	readFullReferenceJSON(t, "testdata/support-verdicts.json", &reference)
	if reference.Count != 1584 || len(reference.Files) != 4 {
		t.Fatal("independent realization support inventory changed")
	}
	count := 0
	for index, file := range reference.Files {
		if file != fmt.Sprintf("support-verdicts-%02d.json", index+1) {
			t.Fatal("unexpected support shard")
		}
		var cases []supportReferenceCase
		readFullReferenceJSON(t, "testdata/"+file, &cases)
		for _, c := range cases {
			t.Run(fmt.Sprintf("%s/%04d", c.Kind, count), func(t *testing.T) {
				admitted := referenceSupportResult(t, c)
				if admitted != c.Admitted {
					t.Fatalf("support differs from Python (admitted=%v)", c.Admitted)
				}
			})
			count++
		}
	}
	if count != reference.Count {
		t.Fatal("support reference cases missing")
	}
}

type supportReferenceCase struct {
	Kind         string          `json:"kind"`
	Requirement  json.RawMessage `json:"requirement"`
	Declarations json.RawMessage `json:"declarations"`
	Capability   json.RawMessage `json:"capability"`
	Demand       json.RawMessage `json:"demand"`
	Admitted     bool            `json:"admitted"`
}

func referenceSupportResult(t *testing.T, c supportReferenceCase) bool {
	t.Helper()
	var admitted bool
	switch c.Kind {
	case "support":
		requirement := decodeRuleObject(t, string(c.Requirement))
		declarations := decodeRuleObject(t, string(c.Declarations))
		inventory := materializationInventory{execution: materializationExecution{manifest: map[string]any{"realization_support": declarations}}}
		admitted = inventory.preparedSupport(requirement) == nil
	case "process":
		capability := decodeRuleObject(t, string(c.Capability))
		demand := decodeRuleObject(t, string(c.Demand))
		admitted = materializationProcessDemands([]any{demand}, []any{capability})
	default:
		t.Fatal("unknown reference owner")
	}
	return admitted
}
