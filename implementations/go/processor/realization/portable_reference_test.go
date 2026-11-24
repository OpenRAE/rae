package realization

import (
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type portableRelationLibrary struct {
	Plans        map[string]binding.ProvisioningPlanV1     `json:"plans"`
	Snapshots    map[string]binding.RuntimeSnapshotV1      `json:"snapshots"`
	Manifests    map[string]binding.BackendManifestV2      `json:"manifests"`
	Envelopes    map[string]*binding.RealizationEnvelopeV1 `json:"envelopes"`
	Requirements map[string][]relationRequirement          `json:"requirements"`
	Cases        []relationCase                            `json:"cases"`
}

func TestPortableRealizationKeepsIndependentAuthorityAndReadbackReference(t *testing.T) {
	library := portableReferenceLibrary(t)
	for _, test := range library.Cases {
		t.Run(test.Name, func(t *testing.T) { checkPortableRelationReference(t, library, test) })
	}
}

func portableReferenceLibrary(t *testing.T) portableRelationLibrary {
	t.Helper()
	var library portableRelationLibrary
	readRelationReferenceParts(t, []string{"testdata/portable-realization-reference.json", "testdata/portable-realization-reference-2.json"}, &library)
	if len(library.Plans) != 19 || len(library.Snapshots) != 32 || len(library.Manifests) != 5 || len(library.Envelopes) != 2 || len(library.Requirements) != 15 || len(library.Cases) != 62 {
		t.Fatal("portable reference inventory changed")
	}
	return library
}

func checkPortableRelationReference(t *testing.T, library portableRelationLibrary, test relationCase) {
	t.Helper()
	plan := library.Plans[test.Plan]
	options := EvaluationOptions{Envelope: library.Envelopes[test.Envelope]}
	if test.Manifest != "" {
		manifest := library.Manifests[test.Manifest]
		options.Manifest = &manifest
	}
	result := Evaluation{Diagnostics: nil, Provenance: []Provenance{}}
	var err error
	switch test.Relation {
	case "planned-evaluate":
		result, err = EvaluatePlanned(plan, library.Snapshots[test.Snapshot], options)
	case "planned-diagnostics":
		result.Diagnostics, err = PlannedAuthorityDiagnostics(plan, options)
	case "planned-cleanup":
		result.Diagnostics, err = CleanupPlannedDiagnostics(plan, library.Snapshots[test.Snapshot], relationRequirements(t, library.Requirements[test.Requirements]), options)
	case "planned-requirements":
		checkPortableRequirementsReference(t, plan, relationRequirements(t, library.Requirements[test.Requirements]))
		return
	default:
		t.Fatalf("unknown pure portable relation %s", test.Relation)
	}
	requireNoError(t, err)
	if test.Relation == "planned-evaluate" && helperOnlyOSContextRefused(t, test.Name, plan, library.Snapshots[test.Snapshot], options) {
		views, viewErr := PlannedRequirements(plan)
		requireNoError(t, viewErr)
		assertHelperOnlyOSContextRefusal(t, views, result)
		return
	}
	if diff := cmp.Diff(test.Diagnostics, referenceDiagnostics(result.Diagnostics)); diff != "" {
		t.Fatalf("portable findings differ (-reference +native):\n%s", diff)
	}
	projected := make([]map[string]string, len(result.Provenance))
	for index, p := range result.Provenance {
		projected[index] = map[string]string{"Address": p.Address, "FieldPath": p.FieldPath, "Domain": p.Domain, "Kind": p.Kind, "Posture": p.Posture, "Provenance": p.Provenance, "GoverningScope": p.GoverningScope}
	}
	if diff := cmp.Diff(test.Provenance, projected); diff != "" {
		t.Fatalf("portable provenance differs (-reference +native):\n%s", diff)
	}
}

func checkPortableRequirementsReference(t *testing.T, plan binding.ProvisioningPlanV1, expected []Requirement) {
	t.Helper()
	actual, err := PlannedRequirements(plan)
	requireNoError(t, err)
	if len(actual) != len(expected) {
		t.Fatalf("recovered views=%d,expected=%d", len(actual), len(expected))
	}
	for index, want := range expected {
		wanted, err := AdmitRequirement(want)
		requireNoError(t, err)
		got, err := AdmitRequirement(actual[index])
		requireNoError(t, err)
		if diff := cmp.Diff(wanted.Document(), got.Document()); diff != "" {
			t.Fatalf("recovered view%d differs (-reference +native):\n%s", index, diff)
		}
	}
}
