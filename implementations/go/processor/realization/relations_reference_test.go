package realization

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type relationRequirement struct {
	Address              string          `json:"address"`
	FieldPath            string          `json:"field_path"`
	Kind                 string          `json:"requirement_kind"`
	Domain               string          `json:"domain"`
	GoverningScope       string          `json:"governing_scope"`
	Provenance           string          `json:"provenance"`
	Posture              *string         `json:"explicitness"`
	ValueDomain          json.RawMessage `json:"value_domain"`
	Constraint           json.RawMessage `json:"constraint_document"`
	Structure            json.RawMessage `json:"structure"`
	Artifact             json.RawMessage `json:"artifact_requirement"`
	ObservationScope     string          `json:"verification_scope"`
	ObservationStrength  string          `json:"required_observation_strength"`
	RecursivePending     bool            `json:"recursive_pending"`
	Delegated            bool            `json:"delegated"`
	ConstraintProvenance string          `json:"constraint_provenance"`
	ConstraintBinding    string          `json:"constraint_binding"`
	StructureError       bool            `json:"structure_error"`
	ValueConstraints     []struct {
		IdentityDigest string          `json:"identity_digest"`
		Leaf           string          `json:"leaf"`
		Parameter      []string        `json:"parameter"`
		AllowedValues  json.RawMessage `json:"allowed_values"`
	} `json:"value_constraints"`
	ProcessResourceLimits []struct {
		IdentityDigest string          `json:"identity_digest"`
		Resource       string          `json:"resource"`
		Scope          string          `json:"scope"`
		Soft           json.RawMessage `json:"soft"`
		Hard           json.RawMessage `json:"hard"`
	} `json:"process_resource_limits"`
}
type relationCase struct {
	Name         string                `json:"name"`
	Relation     string                `json:"relation"`
	Requirements string                `json:"requirements"`
	Plan         string                `json:"plan"`
	Snapshot     string                `json:"snapshot"`
	Manifest     string                `json:"manifest"`
	Envelope     string                `json:"envelope"`
	Diagnostics  []referenceDiagnostic `json:"diagnostics"`
	Provenance   []map[string]string   `json:"provenance"`
}
type relationLibrary struct {
	Requirements map[string][]relationRequirement          `json:"requirements"`
	Plans        map[string]binding.ProvisioningPlanV1     `json:"plans"`
	Snapshots    map[string]binding.RuntimeSnapshotV1      `json:"snapshots"`
	Manifests    map[string]binding.BackendManifestV2      `json:"manifests"`
	Envelopes    map[string]*binding.RealizationEnvelopeV1 `json:"envelopes"`
	Cases        []relationCase                            `json:"cases"`
}

func relationRequirements(t *testing.T, input []relationRequirement) []Requirement {
	t.Helper()
	result := make([]Requirement, len(input))
	for index, record := range input {
		if len(record.Artifact) != 0 && !bytes.Equal(record.Artifact, []byte("null")) {
			t.Fatal("artifact relation fixtures use their dedicated transport owner")
		}
		entry := Requirement{Address: record.Address, FieldPath: record.FieldPath, Kind: record.Kind, Domain: record.Domain, GoverningScope: record.GoverningScope, Provenance: record.Provenance, Posture: record.Posture, ObservationScope: record.ObservationScope, ObservationStrength: record.ObservationStrength, RecursivePending: record.RecursivePending, Delegated: record.Delegated, ConstraintProvenance: record.ConstraintProvenance, ConstraintBinding: record.ConstraintBinding, StructureError: record.StructureError}
		entry.ValueDomain = relationFragment(t, record.ValueDomain, admission.RealizationValue)
		entry.Constraint = relationFragment(t, record.Constraint, admission.RealizationConstraint)
		entry.Structure = relationFragment(t, record.Structure, admission.RealizationStructure)
		for _, bound := range record.ValueConstraints {
			entry.ValueConstraints = append(entry.ValueConstraints, ValueConstraint{IdentityDigest: bound.IdentityDigest, Leaf: bound.Leaf, Parameter: bound.Parameter, AllowedValues: relationFragment(t, bound.AllowedValues, admission.RealizationValue)})
		}
		for _, limit := range record.ProcessResourceLimits {
			entry.ProcessResourceLimits = append(entry.ProcessResourceLimits, ProcessResourceLimit{IdentityDigest: limit.IdentityDigest, Resource: limit.Resource, Scope: limit.Scope, Soft: relationFragment(t, limit.Soft, admission.RealizationValue), Hard: relationFragment(t, limit.Hard, admission.RealizationValue)})
		}
		result[index] = entry
	}
	return result
}

//nolint:ireturn // Reference fixtures must receive the same opaque native fragment as callers.
func relationFragment(t *testing.T, raw []byte, profile admission.FragmentProfile) admission.Fragment {
	t.Helper()
	if len(raw) == 0 || bytes.Equal(raw, []byte("null")) {
		return nil
	}
	owner, err := realizationOwner()
	requireNoError(t, err)
	document, err := nativeValue(raw)
	requireNoError(t, err)
	fragment, err := admission.AdmitFragment(owner, profile, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	requireNoError(t, err)
	return fragment
}

func TestPureRealizationRelationsKeepReferenceDefectCases(t *testing.T) {
	var library relationLibrary
	readRelationReferenceParts(t, []string{
		"testdata/relations-reference.json", "testdata/relations-reference-2.json", "testdata/relations-reference-3.json",
		"testdata/relations-reference-4.json", "testdata/relations-reference-5.json", "testdata/relations-reference-6.json",
		"testdata/relations-reference-7.json", "testdata/relations-reference-8.json", "testdata/relations-reference-9.json",
	}, &library)
	if len(library.Requirements) != 219 || len(library.Plans) != 28 || len(library.Snapshots) != 73 || len(library.Manifests) != 199 || len(library.Envelopes) != 1 || len(library.Cases) != 469 {
		t.Fatal("relation reference inventory changed")
	}
	for _, test := range library.Cases {
		t.Run(test.Name, func(t *testing.T) { checkRelationReference(t, library, test) })
	}
}
func readRelationReferenceParts(t *testing.T, paths []string, result any) {
	t.Helper()
	for _, path := range paths {
		raw, err := os.ReadFile(path) //nolint:gosec // Callers supply fixed repository fixture paths.
		requireNoError(t, err)
		requireNoError(t, json.Unmarshal(raw, result))
	}
}
func checkRelationReference(t *testing.T, library relationLibrary, test relationCase) {
	t.Helper()
	requirements := relationRequirements(t, library.Requirements[test.Requirements])
	manifest := library.Manifests[test.Manifest]
	if test.Relation == "support" {
		result, err := Resolve(requirements, nil, ResolveOptions{Manifest: manifest, Envelope: library.Envelopes[test.Envelope]})
		requireNoError(t, err)
		if diff := cmp.Diff(test.Diagnostics, referenceDiagnostics(result.Diagnostics)); diff != "" {
			t.Fatalf("support differs (-reference +native):\n%s", diff)
		}
		return
	}
	var selected *binding.BackendManifestV2
	if test.Manifest != "" {
		selected = &manifest
	}
	options := EvaluationOptions{Manifest: selected, Envelope: library.Envelopes[test.Envelope]}
	result, err := Evaluate(requirements, library.Plans[test.Plan], library.Snapshots[test.Snapshot], options)
	requireNoError(t, err)
	if helperOnlyOSContextRefused(t, test.Name, library.Plans[test.Plan], library.Snapshots[test.Snapshot], options) {
		assertHelperOnlyOSContextRefusal(t, requirements, result)
		return
	}
	if diff := cmp.Diff(test.Diagnostics, referenceDiagnostics(result.Diagnostics)); diff != "" {
		t.Fatalf("evaluation differs (-reference +native):\n%s", diff)
	}
	provenance := make([]map[string]string, len(result.Provenance))
	for index, entry := range result.Provenance {
		provenance[index] = map[string]string{"Address": entry.Address, "FieldPath": entry.FieldPath, "Domain": entry.Domain, "Kind": entry.Kind, "Posture": entry.Posture, "Provenance": entry.Provenance, "GoverningScope": entry.GoverningScope}
	}
	if diff := cmp.Diff(test.Provenance, provenance); diff != "" {
		t.Fatalf("provenance differs (-reference +native):\n%s", diff)
	}
}
