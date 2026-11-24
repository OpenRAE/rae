package realization_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestArchitectureDomainsUseNativeCanonicalValues(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: architecture
variables:
  arch: {type: string, default: amd64, allowed_values: [amd64, arm64, x86_64]}
nodes:
  host: {type: compute, architecture: '${arch}'}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := realization.Compile(instance)
	if err != nil {
		t.Fatal(err)
	}
	for _, requirement := range compiled.Requirements {
		if requirement.Kind != "node-architecture" {
			continue
		}
		if requirement.Constraint == nil {
			t.Fatalf("architecture constraint missing: %+v", requirement)
		}
		root := requireType[map[string]any](t, requireType[map[string]any](t, requirement.Constraint.Document())["root"])
		values := requireType[[]any](t, requireType[map[string]any](t, root["domain"])["values"])
		if len(values) != 2 || values[0] != "x86_64" || values[1] != "aarch64" {
			t.Fatalf("architecture domain=%v", values)
		}
		if requirement.ValueDomain != nil {
			t.Fatal("recursive architecture domain became a legacy OS bound")
		}
		return
	}
	t.Fatal("architecture requirement missing")
}
