package parity

import (
	"encoding/json"
	"maps"
	"os"
	"slices"
	"strconv"
	"testing"
)

// TestCorpus checks each command that has a runner against the corpus. It
// skips each command without a runner, so its output reports the commands
// that the Go implementation does not cover yet.
func TestCorpus(t *testing.T) {
	cases, err := Load(os.DirFS("testdata"))
	if err != nil {
		t.Fatalf("Load(testdata) error = %v", err)
	}
	if err = checkCorpusInventory(os.DirFS("testdata"), cases); err != nil {
		t.Fatal(err)
	}
	byKey := map[string][]Case{}
	for _, c := range cases {
		byKey[c.Key()] = append(byKey[c.Key()], c)
	}
	registered := runners()
	var inventory struct {
		Implemented []string `json:"implemented"`
	}
	if err = decodeFile(os.DirFS("."), "runner-inventory.json", &inventory); err != nil {
		t.Fatalf("read implemented inventory: %v", err)
	}
	complete := false
	if value, ok := os.LookupEnv("RAES_PARITY_REQUIRE_COMPLETE"); ok {
		complete, err = strconv.ParseBool(value)
		if err != nil {
			t.Fatalf("RAES_PARITY_REQUIRE_COMPLETE: %v", err)
		}
	}
	if err := checkCoverage(cases, registered, inventory.Implemented, complete); err != nil {
		t.Fatal(err)
	}
	for _, key := range slices.Sorted(maps.Keys(byKey)) {
		t.Run(key, func(t *testing.T) {
			run, ok := registered[key]
			if !ok {
				t.Skipf("no Go runner covers %q (%d cases)", key, len(byKey[key]))
			}
			checkCases(t, run, byKey[key])
		})
	}
}

// checkCases runs each case and compares its result with the recorded result.
func checkCases(t *testing.T, run Runner, cases []Case) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) {
			got, err := run(t.Context(), c)
			if err != nil {
				t.Fatalf("run(%s) error = %v", c.Name, err)
			}
			diff, err := compareResults(expectedResult(t, c), got)
			if err != nil {
				t.Fatalf("compareResults() error = %v", err)
			}
			if diff != "" {
				t.Errorf("run(%s) result mismatch (-want +got):\n%s", c.Name, diff)
			}
		})
	}
}

func expectedResult(t *testing.T, c Case) json.RawMessage {
	t.Helper()
	expected := c.Result
	decision := ""
	switch c.Key() {
	case "primitive ingress-exception":
		decision = "maintainer-1822-2026-11-02"
	case "shared carrier":
		decision = "maintainer-1779-2026-10-31"
	}
	if decision != "" {
		var governed struct {
			Decision  string          `json:"decision"`
			Go        json.RawMessage `json:"go"`
			Reference json.RawMessage `json:"reference"`
		}
		if err := json.Unmarshal(expected, &governed); err != nil {
			t.Fatal(err)
		}
		if governed.Decision != decision || len(governed.Reference) == 0 {
			t.Fatal("compatibility case has no approved decision or reference outcome")
		}
		expected = governed.Go
	}
	return expected
}
