package admission

import (
	"encoding/json"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestManifestCapabilityModelReferenceVerdicts(t *testing.T) {
	checkModelRecording(t, "testdata/capability-model-verdicts.json", 70, 5)
}

func TestResourceBudgetModelReferenceVerdicts(t *testing.T) {
	checkModelRecording(t, "testdata/resource-model-verdicts.json", 28, 4)
}

func TestResourceProfileReferenceVerdicts(t *testing.T) {
	checkModelRecording(t, "testdata/resource-profile-verdicts.json", 45, 2)
}

func TestDomainProfileModelReferenceVerdicts(t *testing.T) {
	checkModelRecording(t, "testdata/domain-profile-model-verdicts.json", 30, 5)
}

func checkModelRecording(t *testing.T, file string, cases, baselines int) {
	t.Helper()
	e := boundTestOwner(t)
	raw, err := fs.ReadFile(os.DirFS("."), file)
	if err != nil {
		t.Fatal(err)
	}
	var recorded capabilityRecording
	if err = json.Unmarshal(raw, &recorded); err != nil {
		t.Fatal(err)
	}
	if len(recorded.Cases) != cases || len(recorded.Baselines) != baselines {
		t.Fatal("capability model reference inventory changed")
	}
	for _, c := range recorded.Cases {
		t.Run(c.Name, func(t *testing.T) { checkCapabilityCase(t, e, recorded, c) })
	}
}

type capabilityChange struct {
	Path   []string        `json:"path"`
	Delete bool            `json:"delete"`
	Value  json.RawMessage `json:"value"`
}
type capabilityCase struct {
	Name       string             `json:"name"`
	ContractID string             `json:"contract_id"`
	Baseline   string             `json:"baseline"`
	Valid      bool               `json:"valid"`
	Changes    []capabilityChange `json:"changes"`
}
type capabilityRecording struct {
	Baselines map[string]struct {
		ContractID string          `json:"contract_id"`
		Payload    json.RawMessage `json:"payload"`
	} `json:"baselines"`
	Cases []capabilityCase `json:"cases"`
}

func checkCapabilityCase(t *testing.T, e *Validator, recorded capabilityRecording, c capabilityCase) {
	t.Helper()
	baseline, present := recorded.Baselines[c.Baseline]
	if !present || baseline.ContractID != c.ContractID {
		t.Fatal("missing independent baseline")
	}
	root := decodeRuleObject(t, string(baseline.Payload))
	for _, change := range c.Changes {
		applyCapabilityChange(t, root, change)
	}
	_, err := e.Validate(c.ContractID, controlJSON(t, root), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
	if (err == nil) != c.Valid {
		t.Fatalf("capability admission=%v reference=%v error=%v", err == nil, c.Valid, err)
	}
}

func applyCapabilityChange(t *testing.T, root any, change capabilityChange) {
	t.Helper()
	if len(change.Path) == 0 {
		t.Fatal("missing model change path")
	}
	parent := object(at(root, change.Path[:len(change.Path)-1]...))
	if parent == nil {
		t.Fatal("model change parent is missing")
	}
	key := change.Path[len(change.Path)-1]
	if change.Delete {
		if _, present := parent[key]; !present {
			t.Fatal("model change deletes a missing member")
		}
		delete(parent, key)
	} else {
		parent[key] = decodeRuleObject(t, string(change.Value))
	}
}
