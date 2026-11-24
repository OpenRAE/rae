package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func TestRealizationOpenOfferCannotClaimARestrictedDimensionIsUniversal(t *testing.T) {
	owner, err := New()
	requireNoError(t, err)
	findings, err := RealizationOpenOfferDiagnostics(owner, preparedEnvelopeFixture(t, "exact"), []string{"nodes.host.runtime.database_services[0].engine"})
	if err != nil || len(findings) != 1 || findings[0].Code != "realization-envelope.subsumption.requested-unconstrained" {
		t.Fatalf("restricted offer claimed universal open dimension: %+v %v", findings, err)
	}
}

func TestRealizationMemberKeepsIndependentBindingAndRecordOrder(t *testing.T) {
	raw, err := os.ReadFile("testdata/processor/envelope-member-order.json")
	requireNoError(t, err)
	var cases []struct {
		Name        string                        `json:"name"`
		Envelope    binding.RealizationEnvelopeV1 `json:"envelope"`
		Projection  any                           `json:"projection"`
		Diagnostics []struct {
			Code    string `json:"code"`
			Address string `json:"address"`
			Message string `json:"message"`
		} `json:"diagnostics"`
	}
	requireNoError(t, json.Unmarshal(raw, &cases))
	owner, err := New()
	requireNoError(t, err)
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) {
			findings, err := RealizationMemberDiagnostics(owner, c.Envelope, offerTestValue(t, owner, c.Projection), nil)
			requireNoError(t, err)
			if len(findings) != len(c.Diagnostics) {
				t.Fatalf("native findings=%+v reference=%+v", findings, c.Diagnostics)
			}
			for index, expected := range c.Diagnostics {
				actual := findings[index]
				if actual.Code != expected.Code || actual.Address != expected.Address || actual.Message != expected.Message {
					t.Fatalf("native finding=%+v reference=%+v", actual, expected)
				}
			}
		})
	}
}

func TestRealizationMemberReportsMissingAndMismatchedNativeValues(t *testing.T) {
	owner, err := New()
	requireNoError(t, err)
	envelope := preparedEnvelopeFixture(t, "exact")
	for _, test := range []struct{ engine, code string }{{"sqlite", ""}, {"postgresql", "realization-envelope.membership.domain-mismatch"}, {"", "realization-envelope.membership.path-absent"}} {
		t.Run(test.engine, func(t *testing.T) {
			row := map[string]any{}
			if test.engine != "" {
				row["engine"] = test.engine
			}
			actual := offerTestValue(t, owner, map[string]any{"nodes": map[string]any{"host": map[string]any{"runtime": map[string]any{"database_services": []any{row}}}}})
			findings, err := RealizationMemberDiagnostics(owner, envelope, actual, nil)
			requireNoError(t, err)
			checkRealizationMemberFinding(t, findings, test.code)
		})
	}
}

func checkRealizationMemberFinding(t *testing.T, findings []diagnostic.Diagnostic, code string) {
	t.Helper()
	if code == "" {
		if len(findings) != 0 {
			t.Fatal(findings)
		}
		return
	}
	if len(findings) != 1 || findings[0].Code != code {
		t.Fatalf("native membership diagnostics=%+v", findings)
	}
}
