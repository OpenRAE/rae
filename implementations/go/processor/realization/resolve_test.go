package realization

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func fixtureManifest(t *testing.T) binding.BackendManifestV2 {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	requireNoError(t, err)
	var result binding.BackendManifestV2
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func TestRealizationResolutionLowersRetainedSourceUnderFrozenDecision(t *testing.T) {
	compiled := compileRealizationFixture(t, `name: example
realization: {default: unspecified}
nodes:
  server:
    type: compute
    runtime:
      environment: [{name: TOKEN, value: example, value_classification: plain}]
`)
	pending := requireTestRequirement(t, compiled, "runtime-environment")

	if !pending.RecursivePending || pending.Constraint != nil {
		t.Fatalf("source was not deferred: %+v", pending)
	}
	options := ResolveOptions{Manifest: fixtureManifest(t), Decisions: []Decision{{Address: pending.Address, FieldPath: pending.FieldPath, Kind: pending.Kind, Closure: "open-world"}}}
	result, err := Resolve(compiled.Requirements, compiled.Authority, options)
	requireNoError(t, err)
	var lowered *Requirement
	for i := range result.Requirements {
		if result.Requirements[i].Kind == pending.Kind {
			lowered = &result.Requirements[i]
		}
	}
	assertLoweredOpenRequirement(t, lowered)

	for _, authority := range result.Authority {
		if authority.Concern == pending.Kind && (authority.Delegated || authority.Posture != "open") {
			t.Fatalf("authority=%+v", authority)
		}
	}
	if !pending.RecursivePending || pending.Constraint != nil {
		t.Fatal("resolution mutated compiled source")
	}
	options.Decisions = append(options.Decisions, options.Decisions[0])
	if _, err := Resolve(compiled.Requirements, compiled.Authority, options); err == nil {
		t.Fatal("duplicate decisions accepted")
	}
}

func TestRealizationResolutionChecksExactAndObservationSupport(t *testing.T) {
	manifest := fixtureManifest(t)
	tests := []struct{ kind, scope, want string }{{"node-type", "", ""}, {"runtime-environment", "configuration", "realization.unsupported-exact-requirement"}, {"os-family", "presence", "realization.under-observed-exact-requirement"}}
	for _, tt := range tests {
		t.Run(tt.kind, func(t *testing.T) {
			requirement := exactRequirement("provision.node.server", "nodes.server.type", tt.kind, "author-declared", "#/nodes/server/type")
			requirement.ObservationScope = tt.scope
			result, err := Resolve([]Requirement{requirement}, nil, ResolveOptions{Manifest: manifest})
			requireNoError(t, err)
			if tt.want == "" {
				if len(result.Diagnostics) > 0 {
					t.Fatalf("unexpected findings: %+v", result.Diagnostics)
				}
				return
			}
			if len(result.Diagnostics) != 1 || result.Diagnostics[0].Code != tt.want {
				t.Fatalf("findings=%+v want=%s", result.Diagnostics, tt.want)
			}
		})
	}
}

func TestRealizationResolutionBindsCompleteEnvelopeIdentity(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/realization-envelope/realization-envelope-v1/valid/generic.json")
	requireNoError(t, err)
	var envelope binding.RealizationEnvelopeV1
	if json.Unmarshal(raw, &envelope) != nil {
		t.Fatal("invalid fixture")
	}
	manifest := fixtureManifest(t)
	encoded, err := json.Marshal(manifest)
	requireNoError(t, err)
	var document map[string]json.RawMessage
	if json.Unmarshal(encoded, &document) != nil {
		t.Fatal("invalid manifest")
	}
	versions := sourceValue(manifest.SupportedContractVersions)
	versions = append(versions, "realization-envelope-v1")
	document["supported_contract_versions"] = requireJSON(t, versions)
	identity := map[string]string{"envelope_id": sourceValue(envelope.Id), "digest": sourceValue(envelope.Digest), "configuration_digest": sourceValue(sourceValue(envelope.Configuration).ConfigurationDigest)}
	document["realization_envelope"] = requireJSON(t, identity)
	encoded, err = json.Marshal(document)
	requireNoError(t, err)
	if json.Unmarshal(encoded, &manifest) != nil {
		t.Fatal("invalid identity manifest")
	}
	if _, err := Resolve(nil, nil, ResolveOptions{Manifest: manifest}); err == nil {
		t.Fatal("identity-only target accepted")
	}
	if _, err := Resolve(nil, nil, ResolveOptions{Manifest: manifest, Envelope: &envelope}); err != nil {
		t.Fatal(err)
	}
	identity["configuration_digest"] = "sha256:" + strings.Repeat("f", 64)
	document["realization_envelope"] = requireJSON(t, identity)
	encoded = requireJSON(t, document)
	if json.Unmarshal(encoded, &manifest) != nil {
		t.Fatal("invalid mismatch manifest")
	}
	if _, err := Resolve(nil, nil, ResolveOptions{Manifest: manifest, Envelope: &envelope}); err == nil {
		t.Fatal("changed configuration identity accepted")
	}
}

func TestRealizationResolutionAcceptsAdmittedEnvelopeDefaults(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/realization-envelope/realization-envelope-v1/valid/generic.json")
	requireNoError(t, err)
	var record map[string]json.RawMessage
	if json.Unmarshal(raw, &record) != nil {
		t.Fatal("fixture")
	}
	delete(record, "contract_id")
	delete(record, "schema_version")
	raw, err = json.Marshal(record)
	requireNoError(t, err)
	owner, err := realizationOwner()
	requireNoError(t, err)
	if err := owner.CheckPortable("realization-envelope-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); err != nil {
		t.Fatalf("defaulted fixture not admitted: %v", err)
	}
	var envelope binding.RealizationEnvelopeV1
	if json.Unmarshal(raw, &envelope) != nil {
		t.Fatal("envelope")
	}
	manifest := fixtureManifest(t)
	raw = requireJSON(t, manifest)
	if json.Unmarshal(raw, &record) != nil {
		t.Fatal("manifest")
	}
	versions := append(sourceValue(manifest.SupportedContractVersions), "realization-envelope-v1")
	record["supported_contract_versions"] = requireJSON(t, versions)
	record["realization_envelope"] = requireJSON(t, map[string]string{"envelope_id": sourceValue(envelope.Id), "digest": sourceValue(envelope.Digest), "configuration_digest": sourceValue(sourceValue(envelope.Configuration).ConfigurationDigest)})
	raw = requireJSON(t, record)
	if json.Unmarshal(raw, &manifest) != nil {
		t.Fatal("manifest")
	}
	if _, err := Resolve(nil, nil, ResolveOptions{Manifest: manifest, Envelope: &envelope}); err != nil {
		t.Fatalf("admitted defaults changed target identity: %v", err)
	}
}

func assertLoweredOpenRequirement(t *testing.T, lowered *Requirement) {
	t.Helper()
	if lowered == nil || lowered.RecursivePending || lowered.StructureError || lowered.Constraint == nil || lowered.Posture == nil || *lowered.Posture != "open" {
		t.Fatalf("deferred source not lowered: %+v", lowered)
	}
}
