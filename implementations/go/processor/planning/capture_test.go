package planning

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
)

func TestCaptureAdmissionCannotCombineOffers(t *testing.T) {
	demand := processor.CaptureDemand{DemandID: "events", Address: "evidence_requirements.events", SourceRefs: []string{"nodes.source"}, ScopeRefs: []string{"nodes.scope"}, ExportPolicy: "not-required", Disclosure: "full"}
	offers := []captureOffer{{ID: "source", SourceRefs: []string{"nodes.source"}, ScopeRefs: []string{"other"}, Availability: "available", Fidelity: "complete", Disclosure: "full"}, {ID: "scope", SourceRefs: []string{"other"}, ScopeRefs: []string{"nodes.scope"}, Availability: "available", Fidelity: "complete", Disclosure: "full"}}
	result, err := captureDiagnostics([]processor.CaptureDemand{demand}, offers)
	if err != nil {
		t.Fatal(err)
	}
	if len(result) != 1 || result[0].Code != "capture.scope-ref-mismatch" {
		t.Fatalf("combined separate offers: %+v", result)
	}
	offers[0].ScopeRefs = []string{"nodes.scope"}
	result, err = captureDiagnostics([]processor.CaptureDemand{demand}, offers)
	if err != nil || len(result) != 0 {
		t.Fatalf("complete offer refused: %+v %v", result, err)
	}
	offers[0].ScopeRefs = []string{"*"}
	offers = offers[:1]
	result, err = captureDiagnostics([]processor.CaptureDemand{demand}, offers)
	if err != nil || len(result) != 1 || result[0].Code != "capture.scope-ref-mismatch" {
		t.Fatalf("wildcard scope reference bypassed identity: %+v %v", result, err)
	}
}
