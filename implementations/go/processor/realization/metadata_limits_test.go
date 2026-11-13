package realization

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestRecursiveMetadataRefusalsCannotProducePartialConstraintAuthority(t *testing.T) {
	failure := errors.New("metadata unavailable")
	for _, test := range []struct {
		name             string
		state            concernMetadata
		pending, invalid bool
		wantError        bool
	}{
		{"failed", concernMetadata{err: failure}, false, false, true},
		{"pending", concernMetadata{pending: true}, true, false, false},
		{"invalid", concernMetadata{invalid: true}, false, true, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			r := Requirement{}
			opened, err := test.state.lowerConstraint(&r, nil, nil)
			if opened || (err != nil) != test.wantError || r.RecursivePending != test.pending || r.StructureError != test.invalid || r.Constraint != nil || r.ConstraintBinding != "" {
				t.Fatalf("partial metadata granted constraint authority: %+v %t %v", r, opened, err)
			}
		})
	}
	for _, test := range []struct {
		state concernMetadata
		depth int
	}{{concernMetadata{}, admission.DefaultConstraintLimits().MaxDepth + 1}, {concernMetadata{nodes: admission.DefaultConstraintLimits().MaxNodes}, 0}} {
		state := test.state
		state.collect(nil, nil, "", "", "", test.depth)
		if !state.invalid {
			t.Fatal("over-budget metadata traversal accepted")
		}
	}
}

func TestArchitectureDomainsNormalizeAliasesAndKeepFiniteChoices(t *testing.T) {
	s := realizationSource{constraints: map[string]capabilityConstraint{"/nodes/host/architecture": {Values: []json.RawMessage{json.RawMessage(`"x86_64"`), json.RawMessage(`"amd64"`), json.RawMessage(`"arm64"`)}}}}
	domain, err := s.architectureDomain("/nodes/host/architecture")
	if err != nil {
		t.Fatal(err)
	}
	values := requireType[[]any](t, requireType[map[string]any](t, domain.Document())["values"])
	if len(values) != 2 || values[0] != "x86_64" || values[1] != "aarch64" {
		t.Fatalf("architecture aliases were not normalized once: %v", values)
	}
	if value, err := s.architectureDomain("/missing"); err != nil || value != nil {
		t.Fatal("absent architecture domain became a requirement")
	}
	for _, raw := range []json.RawMessage{json.RawMessage(`{`), json.RawMessage(`7`)} {
		s.constraints["/nodes/host/architecture"] = capabilityConstraint{Values: []json.RawMessage{raw}}
		if _, err := s.architectureDomain("/nodes/host/architecture"); err == nil {
			t.Fatalf("invalid architecture scalar accepted: %s", raw)
		}
	}
}
