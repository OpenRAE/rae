package profile

import (
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func claimFor(profile RelationProfile) BehavioralClaim {
	return BehavioralClaim{TaxonomyID: profile.TaxonomyID, TaxonomyRevision: profile.TaxonomyRevision, RelationID: profile.RelationID, LeftCarrierRef: profile.LeftCarrierRef, RightCarrierRef: profile.RightCarrierRef, ObservationProjectionRef: profile.ObservationProjectionRef, ObservationProjectionRevision: profile.ObservationProjectionRevision, ProfileRef: profile.ID, ProfileRevision: profile.Revision, AssuranceAxis: "model-check"}
}

func TestBehavioralClaimsJoinTheirExactProfile(t *testing.T) {
	p, a := mustLoad(t), mustAuthority(t)
	for _, key := range [][2]string{{"participant-crossing-dpbb-finite-v1", "rev2"}, {"participant-crossing-multi-operation-dpbb-finite-v1", "rev1"}} {
		crossing, err := p.RelationProfile(key[0], key[1])
		if err != nil {
			t.Fatalf("RelationProfile(%s) error = %v", key[0], err)
		}
		claim := claimFor(crossing)
		if err := p.CheckBehavioralClaim(a, claim, nil); err != nil {
			t.Errorf("CheckBehavioralClaim(%s) error = %v, want nil", key[0], err)
		}
		if err := p.CheckBehavioralClaim(a, claim, &crossing); err != nil {
			t.Errorf("CheckBehavioralClaim(%s, supplied) error = %v, want nil", key[0], err)
		}
		mutations := map[string]func(*BehavioralClaim){
			"unknown revision":          func(c *BehavioralClaim) { c.TaxonomyRevision = "rev99" },
			"other taxonomy":            func(c *BehavioralClaim) { c.TaxonomyID = "other-taxonomy" },
			"unknown relation":          func(c *BehavioralClaim) { c.RelationID = "unknown-relation" },
			"missing projection":        func(c *BehavioralClaim) { c.ObservationProjectionRef, c.ObservationProjectionRevision = "", "" },
			"missing profile":           func(c *BehavioralClaim) { c.ProfileRef, c.ProfileRevision = "", "" },
			"missing assurance axis":    func(c *BehavioralClaim) { c.AssuranceAxis = "" },
			"unsupported profile":       func(c *BehavioralClaim) { c.ProfileRef = "unknown-profile" },
			"other profile revision":    func(c *BehavioralClaim) { c.ProfileRevision = "rev9" },
			"other right carrier":       func(c *BehavioralClaim) { c.RightCarrierRef = "other-model" },
			"other left carrier":        func(c *BehavioralClaim) { c.LeftCarrierRef = "other-model" },
			"other projection":          func(c *BehavioralClaim) { c.ObservationProjectionRef = "other-projection" },
			"other projection revision": func(c *BehavioralClaim) { c.ObservationProjectionRevision = "rev9" },
		}
		for name, mutate := range mutations {
			changed := claim
			mutate(&changed)
			if category, code := faultCode(p.CheckBehavioralClaim(a, changed, nil)); category != fault.InvalidInput || code != "behavioral-claim-mismatch" {
				t.Errorf("%s %s: CheckBehavioralClaim() = %s, want InvalidInput behavioral-claim-mismatch", key[0], name, code)
			}
		}
	}
}

func TestSuppliedProfilesJoinTheCatalog(t *testing.T) {
	p, a := mustLoad(t), mustAuthority(t)
	crossing, _ := p.RelationProfile("participant-crossing-dpbb-finite-v1", "rev2")
	claim := claimFor(crossing)
	for name, mutate := range map[string]func(*RelationProfile){
		"profile taxonomy":     func(r *RelationProfile) { r.TaxonomyID = "other-taxonomy" },
		"profile revision":     func(r *RelationProfile) { r.TaxonomyRevision = "rev9" },
		"profile relation":     func(r *RelationProfile) { r.RelationID = "other" },
		"profile identity":     func(r *RelationProfile) { r.ID = "other" },
		"profile left carrier": func(r *RelationProfile) { r.LeftCarrierRef = "other" },
	} {
		supplied := crossing
		mutate(&supplied)
		if err := p.CheckBehavioralClaim(a, claim, &supplied); err == nil {
			t.Errorf("%s: CheckBehavioralClaim(supplied) error = nil, want refusal", name)
		}
	}
	opacity := crossing
	opacity.ParameterKind, opacity.RightCarrierRef = "participant-predicate-opacity/v1", ""
	if err := p.CheckBehavioralClaim(a, claim, &opacity); err != nil {
		t.Errorf("CheckBehavioralClaim(opacity kind ignores the right carrier) error = %v", err)
	}
	catalog := a.CurrentRelationCatalog()
	for _, relation := range catalog.Relations {
		if relation.ProfileRequired {
			continue
		}
		plain := BehavioralClaim{TaxonomyID: catalog.TaxonomyID, TaxonomyRevision: catalog.TaxonomyRevision, RelationID: relation.ID, ObservationProjectionRef: "projection", ObservationProjectionRevision: "rev1"}
		if err := p.CheckBehavioralClaim(a, plain, nil); err != nil {
			t.Errorf("CheckBehavioralClaim(%s) error = %v, want nil", relation.ID, err)
		}
		if err := p.CheckBehavioralClaim(a, plain, &crossing); err == nil {
			t.Errorf("CheckBehavioralClaim(%s, supplied) error = nil, want refusal of an unrequired profile", relation.ID)
		}
		return
	}
	t.Fatal("the current catalog has no relation without a profile")
}

func TestCompletenessMatchesTheReference(t *testing.T) {
	p := mustLoad(t)
	taxonomy := p.CompletenessTaxonomy()
	want := []CompletenessResult{
		{ProfileID: "valid-sdl-fragment", Complete: true, BlockingConcerns: []string{}},
		{ProfileID: "deployable-scenario-intent", BlockingConcerns: []string{"authored-observed-state-separation", "backend-teardown-reconciliation", "credential-intent", "scoped-specificity-open-world-intent"}},
		{ProfileID: "participant-evaluation-scenario", BlockingConcerns: []string{"authored-observed-state-separation", "backend-teardown-reconciliation", "clock-declaration", "credential-intent", "deadlines-and-windows", "flexible-step-tooling", "pacing-and-synchronization", "participant-action-observation", "participant-budgets", "participant-episode-reset", "portable-behavior-contracts", "scoped-specificity-open-world-intent", "temporal-ordering-causality", "time-domain-declaration", "verifier-and-adjudication"}},
		{ProfileID: "controlled-experiment-scenario", BlockingConcerns: []string{"authored-observed-state-separation", "backend-teardown-reconciliation", "clock-declaration", "credential-intent", "deadlines-and-windows", "host-architecture-constraints", "pacing-and-synchronization", "scoped-specificity-open-world-intent", "temporal-ordering-causality", "time-domain-declaration", "verifier-and-adjudication"}},
		{ProfileID: "reproducible-benchmark-study-input", BlockingConcerns: []string{"authored-observed-state-separation", "backend-teardown-reconciliation", "clock-declaration", "credential-intent", "credential-materialization", "deadlines-and-windows", "flexible-step-tooling", "hidden-benchmark-assets", "host-architecture-constraints", "pacing-and-synchronization", "participant-action-observation", "participant-budgets", "participant-episode-reset", "portable-behavior-contracts", "reference-trajectories", "scoped-specificity-open-world-intent", "temporal-ordering-causality", "time-domain-declaration", "verifier-and-adjudication", "weakness-exploitability-semantics"}},
	}
	for _, revision := range []string{"2026-07-12", CurrentAssessmentRevision} {
		assessment, err := p.CompletenessAssessment(revision)
		if err != nil {
			t.Fatalf("CompletenessAssessment(%s) error = %v", revision, err)
		}
		got, err := EvaluateCompleteness(taxonomy, assessment)
		if err != nil {
			t.Fatalf("EvaluateCompleteness(%s) error = %v", revision, err)
		}
		if diff := cmp.Diff(want, got); diff != "" {
			t.Errorf("EvaluateCompleteness(%s) mismatch (-want +got):\n%s", revision, diff)
		}
	}
	if category, code := faultCode(func() error { _, err := p.CompletenessAssessment("2025-01-01"); return err }()); category != fault.NotFound || code != "completeness-assessment-unknown" {
		t.Errorf("CompletenessAssessment(unknown) = %s, want NotFound completeness-assessment-unknown", code)
	}
	checkCompletenessJoins(t, p)
}

func checkCompletenessJoins(t *testing.T, p *Profiles) {
	t.Helper()
	taxonomy := p.CompletenessTaxonomy()
	for name, mutate := range map[string]func(*CompletenessTaxonomy, *CompletenessAssessment){
		"family":            func(_ *CompletenessTaxonomy, a *CompletenessAssessment) { a.ProfileFamily = "other" },
		"taxonomy revision": func(_ *CompletenessTaxonomy, a *CompletenessAssessment) { a.TaxonomyRevision = "other" },
		"missing concern":   func(_ *CompletenessTaxonomy, a *CompletenessAssessment) { delete(a.Statuses, taxonomy.Concerns[0]) },
		"extra concern":     func(_ *CompletenessTaxonomy, a *CompletenessAssessment) { a.Statuses["extra"] = "implemented" },
		"ragged profile": func(x *CompletenessTaxonomy, _ *CompletenessAssessment) {
			delete(x.Profiles[0].Dispositions, taxonomy.Concerns[0])
		},
	} {
		x := p.CompletenessTaxonomy()
		y, _ := p.CompletenessAssessment(CurrentAssessmentRevision)
		mutate(&x, &y)
		if category, code := faultCode(func() error { _, err := EvaluateCompleteness(x, y); return err }()); category != fault.InvalidInput || code != "completeness-join-mismatch" {
			t.Errorf("%s: EvaluateCompleteness() = %s, want InvalidInput completeness-join-mismatch", name, code)
		}
	}
	for _, status := range []string{"external-contract", "partial", "missing"} {
		x := p.CompletenessTaxonomy()
		y, _ := p.CompletenessAssessment(CurrentAssessmentRevision)
		for concern := range y.Statuses {
			y.Statuses[concern] = status
		}
		got, _ := EvaluateCompleteness(x, y)
		if (status == "external-contract") != got[0].Complete {
			t.Errorf("EvaluateCompleteness(all %s) first profile complete = %t", status, got[0].Complete)
		}
	}
}
