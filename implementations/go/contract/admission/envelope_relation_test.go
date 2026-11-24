package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestEnvelopeSubsumptionMatchesPythonReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/backend/subsumption-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []subsumptionReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 7 {
		t.Fatal("reference")
	}
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			checkSubsumptionReference(t, test, owner)
		})
	}
}

func TestEnvelopeUnicodeCarrierChecksReferenceDigestAndTampering(t *testing.T) {
	raw, err := os.ReadFile("testdata/backend/probe-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string                        `json:"name"`
		Envelope binding.RealizationEnvelopeV1 `json:"envelope"`
	}
	if json.Unmarshal(raw, &cases) != nil {
		t.Fatal("fixture")
	}
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		if test.Name == "unicode" {
			checkUnicodeEnvelope(t, owner, test.Envelope)
			return
		}
	}
	t.Fatal("Unicode reference missing")
}
func checkUnicodeEnvelope(t *testing.T, owner *Validator, envelope binding.RealizationEnvelopeV1) {
	t.Helper()
	if _, err := realizationOfferEnvelope(owner, envelope); err != nil {
		t.Fatal("reference Unicode digest refused", err)
	}
	if err := envelope.Digest.UnmarshalJSON([]byte(`"sha256:0000000000000000000000000000000000000000000000000000000000000000"`)); err != nil {
		t.Fatal(err)
	}
	if _, err := realizationOfferEnvelope(owner, envelope); err == nil {
		t.Fatal("tampered digest accepted")
	}
}

func TestEnvelopeRelationsReportNonOverrideableWidening(t *testing.T) {
	var reference struct {
		Envelope    binding.RealizationEnvelopeV1 `json:"envelope"`
		Diagnostics []struct {
			Code    string `json:"code"`
			Address string `json:"address"`
			Message string `json:"message"`
		} `json:"diagnostics"`
	}
	readFullReferenceJSON(t, "testdata/backend/widen-reference.json", &reference)
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	findings, err := EnvelopeSubsumptionDiagnostics(owner, reference.Envelope, reference.Envelope)
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != len(reference.Diagnostics) {
		t.Fatal(findings)
	}
	for i, want := range reference.Diagnostics {
		if findings[i].Code != want.Code || findings[i].Address != want.Address || findings[i].Message != want.Message {
			t.Fatal(findings[i], want)
		}
	}
	_, witness, err := EnvelopeWitnessProjection(owner, reference.Envelope)
	if err != nil || len(witness) != 1 || witness[0].Code != "realization-envelope.invalid.non-overrideable-widen" {
		t.Fatal(witness, err)
	}
}

type subsumptionReference struct {
	Name        string                        `json:"name"`
	Offered     binding.RealizationEnvelopeV1 `json:"offered"`
	Requested   binding.RealizationEnvelopeV1 `json:"requested"`
	Holds       bool                          `json:"holds"`
	Diagnostics []struct {
		Code    string `json:"code"`
		Address string `json:"address"`
		Message string `json:"message"`
	} `json:"diagnostics"`
}

func checkSubsumptionReference(t *testing.T, test subsumptionReference, owner *Validator) {
	t.Helper()
	findings, err := EnvelopeSubsumptionDiagnostics(owner, test.Offered, test.Requested)
	if err != nil {
		t.Fatal(err)
	}
	if (len(findings) == 0) != test.Holds || len(findings) != len(test.Diagnostics) {
		t.Fatalf("diagnostics %+v", findings)
	}
	for i, want := range test.Diagnostics {
		if findings[i].Code != want.Code || findings[i].Address != want.Address || findings[i].Message != want.Message {
			t.Fatalf("finding %+v want %+v", findings[i], want)
		}
	}
}

func TestEnvelopeIntegerBoundsUseReferenceFloatDigest(t *testing.T) {
	var envelope binding.RealizationEnvelopeV1
	readFullReferenceJSON(t, "testdata/backend/integer-bounds-carrier.json", &envelope)
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := realizationOfferEnvelope(owner, envelope); err != nil {
		t.Fatal("reference integer carrier refused", err)
	}
}
