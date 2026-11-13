package realization

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestObservationSupportKeepsScopeAndSourceIndependent(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	requirement, err := admission.AdmitFragment(owner, admission.CompiledRealizationRequirement, map[string]any{"address": "provision.node.server", "field_path": "nodes.server.runtime.environment", "domain": "runtime-realization", "requirement_kind": "runtime-environment", "explicitness": "exact", "provenance": "author-declared", "verification_scope": "configuration", "required_observation_strength": "guest-observed"}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	for _, tt := range []struct {
		scope, source string
		want          bool
	}{{"presence", "guest-observed", false}, {"configuration", "driver-reported", false}, {"configuration", "daemon-observed", false}, {"configuration", "guest-observed", true}} {
		declaration, err := admission.AdmitFragment(owner, admission.RealizationSupport, map[string]any{"domain": "runtime-realization", "support_mode": "open-realization", "disclosure_kinds": []any{"runtime-snapshot-v1"}, "supported_exact_requirement_kinds": []any{"declared-capability-match"}, "observation_capabilities": map[string]any{"runtime-environment": map[string]any{"verification_scope": tt.scope, "observation_strength": tt.source}}}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if err != nil {
			t.Fatal(err)
		}
		got, err := HasRequiredObservationSupport(requirement, []admission.Fragment{declaration}, "runtime-environment")
		if err != nil || got != tt.want {
			t.Fatalf("scope=%s source=%s: %v %v", tt.scope, tt.source, got, err)
		}
	}
	if _, err := HasRequiredObservationSupport(replacedValue{requirement}, nil, "runtime-environment"); err == nil {
		t.Fatal("foreign requirement accepted")
	}
}

func TestObservationManifestKeepsCompleteReferenceTransport(t *testing.T) {
	raw, err := os.ReadFile("testdata/evaluation-reference.json")
	requireNoError(t, err)
	var original struct {
		Manifests map[string]json.RawMessage `json:"manifests"`
	}
	var library evaluationReferenceLibrary
	requireNoError(t, json.Unmarshal(raw, &original))
	requireNoError(t, json.Unmarshal(raw, &library))
	for _, test := range library.Cases {
		if test.Name != "matching-configuration" {
			continue
		}
		expected, err := nativeValue(original.Manifests[test.Manifest])
		requireNoError(t, err)
		actual, err := nativeValue(requireJSON(t, library.Manifests[test.Manifest]))
		requireNoError(t, err)
		if diff := cmp.Diff(expected, actual); diff != "" {
			t.Fatalf("backend observation transport changed (-reference +native):\n%s", diff)
		}
		return
	}
	t.Fatal("missing observation manifest reference")
}

func TestObservationCapabilityUsesPublishedScopeAndNonNoneEvidence(t *testing.T) {
	owner, err := realizationOwner()
	requireNoError(t, err)
	for _, test := range []struct {
		scope, strength string
		accepted        bool
	}{{"configuration", "daemon-observed", true}, {"presence", "driver-reported", true}, {"presence", "none", false}} {
		document := map[string]any{"verification_scope": test.scope, "observation_strength": test.strength}
		err := owner.CheckModelFragment("backend-manifest-v2", "#/$defs/RealizationObservationCapabilityModel", requireJSON(t, document), ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if (err == nil) != test.accepted {
			t.Fatalf("capability admission=%v want=%v", err, test.accepted)
		}
	}
}
