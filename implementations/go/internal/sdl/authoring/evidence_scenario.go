package authoring

import (
	"bytes"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// EvidenceScenario retains the exact admitted authoring phase and its digest.
// Its phase context cannot reopen imports or accept substituted source bytes.
func (p *Parser) EvidenceScenario(document *Document) (admission.EvidenceScenario, error) {
	if p == nil || document == nil || !document.Validated() || document.contract != authoringContract {
		return admission.EvidenceScenario{}, invalid()
	}
	canonical, err := document.CanonicalDigest()
	if err != nil {
		return admission.EvidenceScenario{}, err
	}
	data := document.JSON()
	phase := retainedEvidencePhase{contract: authoringContract, data: data}
	validated, err := p.models.Validate(authoringContract, data, modelLimits(data), phase)
	if err != nil {
		return admission.EvidenceScenario{}, err
	}
	return admission.EvidenceScenario{Value: validated, Digest: canonical}, nil
}

type retainedEvidencePhase struct {
	contract string
	data     []byte
}

func (p retainedEvidencePhase) AdmitSDLPhase(request admission.SDLPhaseRequest) (admission.SDLPhaseAdmission, error) {
	if request.ContractID != p.contract || !bytes.Equal(request.Source, p.data) {
		return admission.SDLPhaseAdmission{}, invalid()
	}
	return admission.SDLPhaseAdmission{ContractID: p.contract, SourceSHA256: digest.SHA256(p.data), Document: slices.Clone(p.data)}, nil
}
