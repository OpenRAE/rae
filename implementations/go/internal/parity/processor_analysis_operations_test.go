package parity

import "testing"

func TestAnalysisRunnersRegistered(t *testing.T) {
	registered := runners()
	for _, key := range []string{"cli processor satisfiability", "cli processor exploit-path"} {
		if registered[key] == nil {
			t.Fatalf("missing runner %s", key)
		}
	}
}
