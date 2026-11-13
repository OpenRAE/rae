package authoring

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestRetainedEvidencePhaseAdmitsOnlyItsExactImmutableInput(t *testing.T) {
	phase := retainedEvidencePhase{contract: authoringContract, data: []byte(`{"name":"retained"}`)}
	request := admission.SDLPhaseRequest{ContractID: authoringContract, Source: []byte(`{"name":"retained"}`)}
	admitted, err := phase.AdmitSDLPhase(request)
	if err != nil {
		t.Fatal(err)
	}
	admitted.Document[0] = 'x'
	if phase.data[0] != '{' {
		t.Fatal("returned document changed retained evidence authority")
	}
	request.Source[0] = 'x'
	if _, err = phase.AdmitSDLPhase(request); err == nil {
		t.Fatal("replacement bytes acquired the retained authoring phase")
	}
	request.Source = phase.data
	request.ContractID = "instantiated-scenario-v1"
	if _, err = phase.AdmitSDLPhase(request); err == nil {
		t.Fatal("replacement contract acquired the retained authoring phase")
	}
}
