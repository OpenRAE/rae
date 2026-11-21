package sdl_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestInstantiationRecordsExplicitAnalysisProfile(t *testing.T) {
	family, err := sdl.Parse([]byte("name: example\nnodes:\n  server: {type: compute}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.InstantiateWithProfile(family, nil, "raes-finite-domain-satisfiability-v1")
	if err != nil {
		t.Fatal(err)
	}
	provenance, ok := instance.Document()["instantiation_provenance"].(map[string]any)
	if !ok || provenance["selected_profile"] != "raes-finite-domain-satisfiability-v1" {
		t.Fatalf("provenance %v", provenance)
	}
	original, err := sdl.Instantiate(family, nil)
	if err != nil {
		t.Fatal(err)
	}
	if requireType[map[string]any](t, original.Document()["instantiation_provenance"])["selected_profile"] != nil {
		t.Fatal("default profile changed")
	}
	if _, err = sdl.InstantiateWithProfile(nil, nil, "profile"); err == nil {
		t.Fatal("nil admitted")
	}
}
