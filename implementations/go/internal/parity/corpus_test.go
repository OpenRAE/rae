package parity

import (
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
	byKey := map[string][]Case{}
	for _, c := range cases {
		byKey[c.Key()] = append(byKey[c.Key()], c)
	}
	registered := runners()
	var inventory struct {
		Implemented    []string `json:"implemented"`
		CorpusComplete bool     `json:"corpus_complete"`
	}
	if err = decodeFile(os.DirFS("."), "coverage.json", &inventory); err != nil {
		t.Fatalf("read implemented inventory: %v", err)
	}
	complete := false
	if value, ok := os.LookupEnv("RAES_PARITY_REQUIRE_COMPLETE"); ok {
		complete, err = strconv.ParseBool(value)
		if err != nil {
			t.Fatalf("RAES_PARITY_REQUIRE_COMPLETE: %v", err)
		}
	}
	if complete && !inventory.CorpusComplete {
		t.Fatal("corpus does not yet cover the full scope of issue #1778")
	}
	if err := checkCoverage(cases, registered, inventory.Implemented, complete); err != nil {
		t.Fatal(err)
	}
	for _, key := range slices.Sorted(maps.Keys(byKey)) {
		t.Run(key, func(t *testing.T) {
			run, ok := registered[key]
			if !ok {
				t.Skipf("no Go runner covers the %d cases yet", len(byKey[key]))
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
			diff, err := compareResults(c.Result, got)
			if err != nil {
				t.Fatalf("compareResults() error = %v", err)
			}
			if diff != "" {
				t.Errorf("run(%s) result mismatch (-want +got):\n%s", c.Name, diff)
			}
		})
	}
}
