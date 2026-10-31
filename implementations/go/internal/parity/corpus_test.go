package parity

import (
	"encoding/json"
	"maps"
	"os"
	"slices"
	"testing"

	"github.com/google/go-cmp/cmp"
)

// TestCorpus checks each command that has a runner against the corpus. It
// skips each command without a runner, so its output reports the commands
// that the Go implementation does not cover yet.
func TestCorpus(t *testing.T) {
	corpus, err := Load(os.DirFS("testdata"))
	if err != nil {
		t.Fatalf("Load(testdata) error = %v", err)
	}
	t.Logf("The corpus has %d cases from Python commit %s.", len(corpus.Cases), corpus.PythonCommit)
	byKey := map[string][]Case{}
	for _, c := range corpus.Cases {
		byKey[c.Key()] = append(byKey[c.Key()], c)
	}
	registered := runners()
	for key := range registered {
		if len(byKey[key]) == 0 {
			t.Errorf("runner %q has no case in the corpus", key)
		}
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
			if diff := cmp.Diff(decode(t, c.Result), decode(t, got)); diff != "" {
				t.Errorf("run(%s) result mismatch (-want +got):\n%s", c.Name, diff)
			}
		})
	}
}

// decode returns the JSON value of a result, so that results compare by value.
func decode(t *testing.T, result json.RawMessage) any {
	t.Helper()
	var value any
	if err := json.Unmarshal(result, &value); err != nil {
		t.Fatalf("json.Unmarshal(%s) error = %v", result, err)
	}
	return value
}
