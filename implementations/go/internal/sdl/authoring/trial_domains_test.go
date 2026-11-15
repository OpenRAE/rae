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
