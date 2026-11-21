package analysis

import (
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestOpacityExplicitProfileIsReadmittedAndBound(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/formal-analysis/participant-opacity-analysis-input-v1/valid/opaque-pair.json")
	if err != nil {
		t.Fatal(err)
	}
	input, err := admitOpacityDocument(&JSONInput{Data: raw}, "participant-opacity-analysis-input-v1", 8<<20)
	if err != nil {
		t.Fatal(err)
	}
	governed, err := loadOpacityProfile(input)
	if err != nil {
		t.Fatal(err)
	}
	// A changed finite bound is an explicit profile, not an ambient packaged replacement.
	object(object(governed["parameters"])["bounds"])["max_points"] = 8192
	encoded, err := canonical(governed)
	if err != nil {
		t.Fatal(err)
	}
	owner, err := analysisOwner()
	if err != nil {
		t.Fatal(err)
	}
	claim, err := canonical(input["claim"])
	if err != nil {
		t.Fatal(err)
	}
	admitted, err := owner.Validate("behavioral-relation-profile-v1", encoded, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, opacityClaimContext{claim: claim})
	if err != nil {
		t.Fatal(err)
	}
	input["profile_digest"], err = hash(governed)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err = canonical(input)
	if err != nil {
		t.Fatal(err)
	}
	request := Request{Kind: "participant-opacity", Input: &JSONInput{Data: encoded, Profile: admitted}}
	if _, err = Analyze(request); err != nil {
		t.Fatal(err)
	}
	request.Input.Profile = validation.Value{}
	if _, err = Analyze(request); err == nil {
		t.Fatal("unpackaged profile selected without explicit authority")
	}
}

func TestOpacityClaimUsesExplicitCatalogRules(t *testing.T) {
	input := testObject(t, readTestFile(t, "../../../../contracts/fixtures/formal-analysis/participant-opacity-model-check-input-v1/valid/opaque-transition-model.json"))
	raw, err := packagedOpacityCatalog(text(object(input["claim"])["taxonomy_revision"]))
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := admitOpacityDocument(&JSONInput{Data: raw}, "behavioral-relations-v1", 8<<20)
	if err != nil {
		t.Fatal(err)
	}
	relation := object(object(catalog["relations"])[text(object(input["claim"])["relation_id"])])
	relation["relation_parameter_profile_required"] = false
	admitted := testAdmission(t, "behavioral-relations-v1", testJSON(t, catalog), nil)
	input["catalog_digest"], err = hash(catalog)
	if err != nil {
		t.Fatal(err)
	}
	_, err = Analyze(Request{Kind: "participant-opacity-model-check", Input: &JSONInput{Data: testJSON(t, input), Catalog: admitted}})
	requireOperational(t, err)
}

func TestOpacityRejectsBinaryAndMultiOperationProfiles(t *testing.T) {
	input := testObject(t, readTestFile(t, "../../../../contracts/fixtures/formal-analysis/participant-opacity-analysis-input-v1/valid/opaque-pair.json"))
	for _, name := range []string{"participant-crossing", "multi-operation-crossing"} {
		t.Run(name, func(t *testing.T) {
			raw := readTestFile(t, "../../../../contracts/fixtures/profiles/behavioral-relation-profile-v1/valid/"+name+".json")
			_, err := readmitOpacityProfile(input, raw, nil)
			requireOperational(t, err)
			// Matching the supplied identity cannot promote binary evidence into
			// the unary opacity lane; native claim admission remains mandatory.
			profile := testObject(t, raw)
			changed := testObject(t, testJSON(t, input))
			changed["profile_id"], changed["profile_revision"] = profile["profile_id"], profile["profile_revision"]
			changed["profile_digest"], err = hash(profile)
			if err != nil {
				t.Fatal(err)
			}
			claim := object(changed["claim"])
			for _, key := range []string{"taxonomy_id", "taxonomy_revision", "relation_id", "left_carrier_ref", "observation_projection_ref", "observation_projection_revision"} {
				claim[key] = profile[key]
			}
			claim["right_carrier_ref"] = object(object(profile["parameters"])["right"])["model_id"]
			claim["relation_parameter_profile_ref"], claim["relation_parameter_profile_revision"] = profile["profile_id"], profile["profile_revision"]
			_, err = readmitOpacityProfile(changed, raw, nil)
			requireOperational(t, err)
		})
	}
}
