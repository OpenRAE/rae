package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestBehavioralProfileLocalJoins(t *testing.T) {
	e := boundTestOwner(t)
	for _, name := range []string{"participant-opacity-baseline", "participant-opacity-runtime-reference", "participant-opacity-theorem", "participant-crossing", "multi-operation-crossing"} {
		profile := fixtureObject(t, "fixtures/profiles/behavioral-relation-profile-v1/valid/"+name+".json")
		rule, ok := e.checker("behavioral-relation-profile-local-join")
		if !ok {
			t.Fatal("missing profile rule")
		}
		if err := rule.check(validation.Invocation{Instance: profile, Root: profile}); err != nil {
			t.Errorf("profile %s: %v", name, err)
		}
	}
	profile := fixtureObject(t, "fixtures/profiles/behavioral-relation-profile-v1/valid/participant-opacity-baseline.json")
	profile["observation_projection_ref"] = "other-projection"
	if err := behavioralProfile(validation.Invocation{Instance: profile}); err == nil {
		t.Error("mismatched projection was accepted")
	}
	profile = fixtureObject(t, "fixtures/profiles/behavioral-relation-profile-v1/valid/participant-crossing.json")
	object(at(profile, "parameters", "right"))["source_digest"] = at(profile, "parameters", "left", "source_digest")
	if err := behavioralProfile(validation.Invocation{Instance: profile}); err == nil {
		t.Error("shared transition authorities were accepted")
	}
}

type testBehavioralContext struct{ claim []byte }

func (c testBehavioralContext) BehavioralClaim() []byte { return c.claim }

func TestBehavioralRevisionedClaims(t *testing.T) {
	e := boundTestOwner(t)
	taxonomy := fixtureObject(t, "fixtures/profiles/scientific-completeness-taxonomy-v1/valid/minimal.json")
	profile := array(at(taxonomy, "profiles"))[0]
	claim := array(at(profile, "behavioral_claims"))[0]
	if err := e.behavioralClaim(claim, nil); err != nil {
		t.Fatal(err)
	}
	object(claim)["quantifier_scope"] = "all-traces"
	if err := e.behavioralClaim(claim, nil); err == nil {
		t.Error("structural evidence supported universal traces")
	}
	object(claim)["quantifier_scope"] = "single-artifact"
	object(claim)["taxonomy_revision"] = "unknown"
	if err := e.behavioralClaim(claim, nil); err == nil {
		t.Error("unknown catalog revision was accepted")
	}
	evidence := fixtureObject(t, "fixtures/formal-analysis/participant-opacity-analysis-evidence-v1/valid/bounded-counterexample.json")
	data, err := json.Marshal(at(evidence, "claim"))
	if err != nil {
		t.Fatal(err)
	}
	instance := e.relationProfiles[join("participant-opacity-baseline-v1", "sem-231/rev2")]
	if err := validateTestDocument(t, e, "behavioral-relation-profile-v1", instance, testBehavioralContext{claim: data}); err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, "behavioral-relation-profile-v1", instance, nil); err == nil {
		t.Error("full profile validation accepted no claim context")
	}
}

func TestBehavioralCatalogAndCompletenessFixture(t *testing.T) {
	e := boundTestOwner(t)
	catalog := fixtureObject(t, "fixtures/concept-authority/behavioral-relations-v1/valid/reference.json")
	if err := behavioralCatalog(validation.Invocation{Instance: catalog}); err != nil {
		t.Fatal(err)
	}
	for _, relation := range object(at(catalog, "relations")) {
		object(relation)["source_refs"] = []any{"missing-bibliography-source"}
	}
	if err := behavioralCatalog(validation.Invocation{Instance: catalog}); err == nil {
		t.Error("dangling bibliography references were accepted")
	}
	taxonomy := fixtureObject(t, "fixtures/profiles/scientific-completeness-taxonomy-v1/valid/minimal.json")
	data, err := json.Marshal(taxonomy)
	if err != nil {
		t.Fatal(err)
	}
	assessment := fixtureObject(t, "fixtures/profiles/scientific-completeness-assessment-v1/valid/minimal.json")
	invocation := validation.Invocation{Instance: assessment, Context: testCompletenessContext{taxonomy: data}}
	if err := validateTestDocument(t, e, "scientific-completeness-assessment-v1", invocation.Instance, invocation.Context); err != nil {
		t.Fatal(err)
	}
	object(assessment)["taxonomy_revision"] = "other"
	if err := validateTestDocument(t, e, "scientific-completeness-assessment-v1", invocation.Instance, invocation.Context); err == nil {
		t.Error("assessment joined another taxonomy revision")
	}
}

type testCompletenessContext struct{ taxonomy []byte }

func (c testCompletenessContext) CompletenessTaxonomy() []byte { return c.taxonomy }
