package profile

import "testing"

func TestComparisonProfileReadmissionRecomputesPinsAndCopiesMaps(t *testing.T) {
	original, err := mustLoad(t).ComparisonProfile("reference-v2")
	if err != nil {
		t.Fatal(err)
	}
	input := original
	input.Digest = "caller-forged"
	got, err := AdmitComparisonProfile(input)
	if err != nil || got.Digest != original.Digest {
		t.Fatalf("readmission=%v %v", got.Digest, err)
	}
	got.OwnerProjectionVersions["scenario"] = "1"
	if input.OwnerProjectionVersions["scenario"] != "2" {
		t.Fatal("readmitted profile shares caller maps")
	}
	input.OwnerProjectionVersions["scenario"] = "unsupported"
	if _, err := AdmitComparisonProfile(input); err == nil {
		t.Fatal("invalid owner admitted")
	}
}
func TestComparisonProfileReadmissionReusesClosedVersionsAndBounds(t *testing.T) {
	changes := []func(*ComparisonProfile){
		func(p *ComparisonProfile) { p.ProfileID = "unknown" },
		func(p *ComparisonProfile) { p.SemanticAxis = "unknown" },
		func(p *ComparisonProfile) { p.Limits.MaxSubjects = 4097 },
		func(p *ComparisonProfile) { p.Limits.MaxDependencyEdges = 8193 },
		func(p *ComparisonProfile) { p.Limits.MaxPathDepth = 33 },
		func(p *ComparisonProfile) { p.Limits.MaxPaths = 4097 },
		func(p *ComparisonProfile) { p.Limits.MaxDiagnostics = 65 },
		func(p *ComparisonProfile) { p.DependencyRuleVersions["scenario-import"] = "2" },
		func(p *ComparisonProfile) { delete(p.OwnerProjectionVersions, "task") },
	}
	for i, change := range changes {
		input, err := mustLoad(t).ComparisonProfile("reference-v2")
		if err != nil {
			t.Fatal(err)
		}
		change(&input)
		if _, err := AdmitComparisonProfile(input); err == nil {
			t.Fatalf("invalid case %d admitted", i)
		}
	}
}
