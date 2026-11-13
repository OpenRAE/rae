package realization

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestResolutionDecisionsRefuseUnknownDuplicateAndUnboundedClosures(t *testing.T) {
	key := requirementIdentity{"provision.node.host", "nodes.host.runtime.environment", "runtime-environment"}
	known := map[requirementIdentity]bool{key: true}
	valid := Decision{Address: key.address, FieldPath: key.path, Kind: key.kind, Closure: termOpenWorld}
	for _, input := range [][]Decision{{{Address: "other", Closure: termOpenWorld}}, {valid, valid}, {{Address: key.address, FieldPath: key.path, Kind: key.kind, Closure: "future"}}} {
		if _, err := resolutionDecisions(input, known); err == nil {
			t.Fatal("unbound or conflicting apparatus decision accepted")
		}
	}
	got, err := resolutionDecisions([]Decision{valid}, known)
	if err != nil || got[key] != termOpenWorld {
		t.Fatal("valid delegated decision lost")
	}
	if _, err := Resolve(make([]Requirement, 16385), nil, ResolveOptions{}); err == nil {
		t.Fatal("unbounded resolution batch accepted")
	}
}

func TestDelegatedAuthorityResolutionCopiesPathsAndRequiresKnownConcern(t *testing.T) {
	authority := Authority{Address: "provision.node.host", FieldPath: "nodes.host.runtime.environment", Concern: "runtime-environment", Delegated: true, PayloadPath: []string{"spec", "node", "runtime", "environment"}}
	key := authorityKey(authority)
	if _, err := resolveAuthority([]Authority{authority}, nil, nil, nil); err == nil {
		t.Fatal("unknown delegated concern acquired authority")
	}
	for _, closure := range []string{"closed-world", termOpenWorld} {
		result, err := resolveAuthority([]Authority{authority}, map[requirementIdentity]bool{key: true}, map[requirementIdentity]string{key: closure}, nil)
		if err != nil || len(result) != 1 || result[0].Delegated {
			t.Fatalf("apparatus decision not frozen: %+v %v", result, err)
		}
		want := termClosed
		if closure == termOpenWorld {
			want = termOpen
		}
		if result[0].Posture != want {
			t.Fatalf("resolved closure=%s, want %s", result[0].Posture, want)
		}
		result[0].PayloadPath[0] = "changed"
		if authority.PayloadPath[0] != "spec" {
			t.Fatal("authority result aliases source path")
		}
	}
	for _, source := range []*compiledConcern{nil, {fieldPath: "other"}, {fieldPath: authority.FieldPath, definition: concernDefinition{kind: "other"}}} {
		requirement := Requirement{Address: authority.Address, FieldPath: authority.FieldPath, Kind: authority.Concern, RecursivePending: true, source: source}
		if _, err := lowerPendingRequirement(&requirement, "closed-world"); err != nil || requirement.RecursivePending || !requirement.StructureError {
			t.Fatalf("missing retained source granted a recursive constraint: %+v %v", requirement, err)
		}
	}
}

func TestResolutionEnvelopeIdentityChecksEveryCommittedCoordinate(t *testing.T) {
	envelope := *processSupportEnvelope(t, "matching")
	identity := map[string]any{"contract_id": "realization-envelope-v1", "schema_version": "realization-envelope/v1", "envelope_id": sourceValue(envelope.Id), "digest": sourceValue(envelope.Digest), "configuration_digest": sourceValue(sourceValue(envelope.Configuration).ConfigurationDigest)}
	if err := checkResolutionEnvelopeIdentity(requireJSON(t, identity), envelope); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"contract_id", "schema_version", "envelope_id", "digest", "configuration_digest"} {
		original := identity[key]
		identity[key] = "changed"
		if checkResolutionEnvelopeIdentity(requireJSON(t, identity), envelope) == nil {
			t.Fatalf("changed envelope %q accepted", key)
		}
		identity[key] = original
	}
	if checkResolutionEnvelopeIdentity(json.RawMessage(`{`), envelope) == nil {
		t.Fatal("invalid identity JSON accepted")
	}
	requirement, manifest, availability, _ := artifactTestFixture(t)
	if findings, supportErr := ArtifactSupport([]Requirement{requirement}, manifest, availability); supportErr != nil || len(findings) != 0 {
		t.Fatalf("target fixture has no valid artifact support: %+v %v", findings, supportErr)
	}
	if checkResolutionTarget(ResolveOptions{Manifest: manifest, Envelope: &envelope}) == nil {
		t.Fatal("supplied apparatus had no manifest commitment")
	}
	if checkResolutionTarget(ResolveOptions{Manifest: binding.BackendManifestV2{}}) == nil {
		t.Fatal("invalid manifest accepted")
	}
}
