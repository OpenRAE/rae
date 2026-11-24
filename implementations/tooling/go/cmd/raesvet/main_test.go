package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"testing"
)

func TestCommandReportsAllNativeAnalyzerFlags(t *testing.T) {
	if os.Getenv("RAES_VET_FLAG_HELPER") == "1" {
		os.Args = []string{"raesvet", "-flags"}
		main()
		return
	}
	command := exec.CommandContext(t.Context(), os.Args[0], "-test.run=^TestCommandReportsAllNativeAnalyzerFlags$") //nolint:gosec // The subprocess re-enters the current Go test executable.
	command.Env = append(os.Environ(), "RAES_VET_FLAG_HELPER=1")
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("analyzer flag command: %v: %s", err, output)
	}
	var flags []struct {
		Name string `json:"Name"`
	}
	if err := json.Unmarshal(output, &flags); err != nil {
		t.Fatalf("analyzer flags are not a JSON array: %v: %s", err, output)
	}
	known := map[string]bool{}
	for _, flag := range flags {
		known[flag.Name] = true
	}
	for _, name := range []string{"getprefix", "gotwant", "wrapverb"} {
		if !known[name] {
			t.Errorf("command does not expose analyzer %q", name)
		}
	}
}
