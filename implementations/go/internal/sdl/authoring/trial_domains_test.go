package authoring

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestTrialScalarDomainsMatchIndependentReferenceBounds(t *testing.T) {
	raw, err := os.ReadFile("testdata/trial-domains-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []trialDomainReferenceCase `json:"cases"`
	}
	if json.Unmarshal(raw, &fixture) != nil {
		t.Fatal("fixture")
	}
	for _, test := range fixture.Cases {
		t.Run(test.Name, func(t *testing.T) { checkTrialDomainReference(t, test) })
	}
}

func TestTrialNamedDomainsKeepCanonicalOrderAndExactBounds(t *testing.T) {
	for _, kind := range []string{termGovernedReference, variationAlternativeKind} {
		t.Run(kind, func(t *testing.T) {
			checkTrialNamedDomain(t, kind)
		})
	}
	if _, err := finiteTrialOutcomes(semanticVariation{Kind: "unknown"}, 2); err == nil {
		t.Fatal("unknown trial domain admitted")
	}
}

type trialDomainReferenceCase struct {
	Name     string                  `json:"name"`
	Domain   semanticVariationDomain `json:"domain"`
	Maximum  int                     `json:"maximum"`
	Outcomes json.RawMessage         `json:"outcomes"`
	Code     string                  `json:"code"`
}

func checkTrialDomainReference(t *testing.T, test trialDomainReferenceCase) {
	t.Helper()

	got, domainErr := finiteScalarTrialOutcomes(test.Domain, test.Maximum)
	if test.Code != "" {
		var owned *fault.Error
		if !errors.As(domainErr, &owned) || owned.Code() != test.Code {
			t.Fatal("domain refusal differs", domainErr)
		}
		return
	}
	if domainErr != nil {
		t.Fatal(domainErr)
	}
	encoded, encodeErr := json.Marshal(got)
	if encodeErr != nil {
		t.Fatal(encodeErr)
	}
	actual, actualErr := canonjson.JCS(encoded)
	want, wantErr := canonjson.JCS(test.Outcomes)
	if actualErr != nil || wantErr != nil || string(actual) != string(want) {
		t.Fatal("finite domain order differs", string(actual), string(want))
	}
}

func checkTrialNamedDomain(t *testing.T, kind string) {
	t.Helper()

	point := semanticVariation{Kind: kind, Domain: semanticVariationDomain{Allowed: []string{"z", "a"}}, Alternatives: map[string]semanticVariationMember{"z": {}, "a": {}}}
	outcomes, err := finiteTrialOutcomes(point, 2)
	if err != nil || len(outcomes) != 2 {
		t.Fatal("finite named domain refused", err)
	}
	field, expectedKind := "reference_id", "reference"
	if kind == variationAlternativeKind {
		field, expectedKind = "member_id", "member"
	}
	for index, name := range []string{"a", "z"} {
		var value map[string]string
		if json.Unmarshal(outcomes[index], &value) != nil || value["kind"] != expectedKind || value[field] != name {
			t.Fatal("named domain order changed", string(outcomes[index]))
		}
	}
	if _, err := finiteTrialOutcomes(point, 1); err == nil {
		t.Fatal("named domain expanded beyond its bound")
	}
	point.Domain.Allowed = nil
	point.Alternatives = nil
	if _, err := finiteTrialOutcomes(point, 2); err == nil {
		t.Fatal("empty named domain admitted")
	}
}
