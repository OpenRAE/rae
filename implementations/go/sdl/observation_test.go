package sdl_test

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestObservationScopesUseNativeDeclarationAndCollectionOwners(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\nnodes:\n  server:\n    type: compute\n    runtime:\n      environment: [{name: PUBLIC, value: example}]\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	profiles := []admission.RealizationCollectionProfile{{FieldPointer: "/nodes/server/runtime/environment", CollectionKind: "runtime-environment", IdentityFields: []string{"name"}, Closure: admission.RealizationClosure{Posture: "closed", Universe: "sdl-collection-members/v1", Profile: "recursive-realization-constraint/v1"}}}
	pointer := "/nodes/server/runtime/environment/0/value"
	result, err := sdl.ObservationScopes(scenario, []string{pointer}, []string{"server"}, profiles)
	if err != nil {
		t.Fatal(err)
	}
	if result["server"] != "/nodes/server" || !strings.Contains(result[pointer], "/@sha256:") {
		t.Fatalf("scopes=%v", result)
	}
	canonical := result[pointer]
	result, err = sdl.ObservationScopes(scenario, []string{canonical}, nil, profiles)
	if err != nil || result[canonical] != canonical {
		t.Fatalf("canonical=%v %v", result, err)
	}
	if _, err := sdl.ObservationScopes(scenario, nil, []string{"missing"}, profiles); err == nil {
		t.Fatal("missing observation subject accepted")
	}
}
