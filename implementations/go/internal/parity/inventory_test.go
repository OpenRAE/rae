package parity

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
	"testing/fstest"
)

func inventoryFixture() (corpusInventory, []Case) {
	var inventory corpusInventory
	inventory.Complete = true
	inventory.Surfaces = map[string][]string{}
	var cases []Case
	for _, surface := range []string{"cli", "mcp", "http", "schema", "canonical", "randstream", "primitive"} {
		inventory.Surfaces[surface] = []string{"command"}
		argument := "distinct-argument"
		if surface == "schema" {
			argument = "command"
		}
		cases = append(cases, Case{Surface: surface, Command: "command", Args: []string{argument}})
	}
	sum := sha256.Sum256([]byte(input))
	inventory.Inputs = []string{"examples/source.yaml"}
	inventory.InputDigests = map[string]string{inventory.Inputs[0]: "sha256:" + hex.EncodeToString(sum[:])}
	cases[0].Files = map[string][]byte{"input.yaml": []byte(input)}
	identity := strings.Repeat("a", 64)
	cases[0].Name = "regression/" + identity
	inventory.Regressions.Complete = true
	inventory.Regressions.TestCount = 1
	inventory.Regressions.InputCount = 1
	inventory.Regressions.Origins = map[string][]string{identity: {"tests/test_one.py::test_case"}}
	inventory.Regressions.SourceIdentity.TestTree = strings.Repeat("b", 40)
	inventory.Regressions.SourceIdentity.PythonTree = strings.Repeat("b", 40)
	inventory.Regressions.SourceIdentity.ContractsTree = strings.Repeat("b", 40)
	inventory.Regressions.SourceIdentity.ExamplesTree = strings.Repeat("b", 40)
	inventory.Regressions.SourceIdentity.EnvironmentSHA256 = strings.Repeat("c", 64)
	inventory.Regressions.SourceIdentity.CollectorSHA256 = strings.Repeat("c", 64)
	return inventory, cases
}

func inventoryFS(t *testing.T, inventory corpusInventory) fstest.MapFS {
	t.Helper()
	content, err := json.Marshal(inventory)
	if err != nil {
		t.Fatal(err)
	}
	return fstest.MapFS{"inventory.json": {Data: content}}
}

func TestCorpusInventoryRequiresActualCoverage(t *testing.T) {
	inventory, cases := inventoryFixture()
	if err := checkCorpusInventory(inventoryFS(t, inventory), cases); err != nil {
		t.Fatalf("checkCorpusInventory(complete) = %v", err)
	}
	for name, mutate := range map[string]func(*corpusInventory){
		"incomplete flag":    func(i *corpusInventory) { i.Complete = false },
		"missing input":      func(i *corpusInventory) { i.MissingInputs = []string{"other"} },
		"empty surface":      func(i *corpusInventory) { delete(i.Surfaces, "mcp") },
		"missing surface":    func(i *corpusInventory) { i.MissingSurface = map[string][]string{"http": {"other"}} },
		"unrecorded command": func(i *corpusInventory) { i.Surfaces["mcp"] = []string{"other"} },
		"empty inputs":       func(i *corpusInventory) { i.Inputs = nil },
		"duplicate inputs": func(i *corpusInventory) {
			i.Inputs = append(i.Inputs, i.Inputs[0])
			i.InputDigests["other"] = "invalid"
		},
		"unrecorded input":    func(i *corpusInventory) { i.InputDigests[i.Inputs[0]] = strings.Repeat("f", 64) },
		"regression flag":     func(i *corpusInventory) { i.Regressions.Complete = false },
		"empty tests":         func(i *corpusInventory) { i.Regressions.TestCount = 0 },
		"empty regressions":   func(i *corpusInventory) { i.Regressions.InputCount = 0 },
		"wrong input count":   func(i *corpusInventory) { i.Regressions.InputCount = 2 },
		"missing test source": func(i *corpusInventory) { i.Regressions.SourceIdentity.TestTree = "" },
		"missing product":     func(i *corpusInventory) { i.Regressions.SourceIdentity.PythonTree = "" },
		"missing contracts":   func(i *corpusInventory) { i.Regressions.SourceIdentity.ContractsTree = "" },
		"missing examples":    func(i *corpusInventory) { i.Regressions.SourceIdentity.ExamplesTree = "" },
		"missing environment": func(i *corpusInventory) { i.Regressions.SourceIdentity.EnvironmentSHA256 = "" },
		"missing collector":   func(i *corpusInventory) { i.Regressions.SourceIdentity.CollectorSHA256 = "" },
		"missing origin":      func(i *corpusInventory) { i.Regressions.Origins[strings.Repeat("a", 64)] = nil },
		"empty origin":        func(i *corpusInventory) { i.Regressions.Origins[strings.Repeat("a", 64)] = []string{""} },
		"missing case": func(i *corpusInventory) {
			i.Regressions.Origins = map[string][]string{strings.Repeat("d", 64): {"tests/test_other.py::test_case"}}
		},
		"invalid case digest": func(i *corpusInventory) {
			i.Regressions.Origins = map[string][]string{"../escape": {"tests/test_other.py::test_case"}}
		},
	} {
		t.Run(name, func(t *testing.T) {
			candidate, candidateCases := inventoryFixture()
			mutate(&candidate)
			if err := checkCorpusInventory(inventoryFS(t, candidate), candidateCases); err == nil {
				t.Error("checkCorpusInventory(incomplete) error = nil")
			}
		})
	}
	if err := checkCorpusInventory(fstest.MapFS{}, cases); err == nil {
		t.Error("checkCorpusInventory(absent inventory) error = nil")
	}
}
