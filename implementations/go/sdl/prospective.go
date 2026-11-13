package sdl

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
)

// ProspectiveContent retains validated common content without admitting an SDL
// document phase. Its byte views are independent copies.
type ProspectiveContent interface {
	JSON() []byte
	ModelJSON() []byte
	prospectiveContent()
}
type prospectiveContent struct{ document *authoring.Document }

func (prospectiveContent) prospectiveContent() {}
func (p prospectiveContent) JSON() []byte      { return p.document.JSON() }
func (p prospectiveContent) ModelJSON() []byte { return p.document.ModelJSON() }

// AdmitProspectiveContent checks common SDL content, including qualified
// declarations and references, through the native constructor and semantics.
//
//nolint:ireturn // The native owner returns a sealed common-content handle.
func AdmitProspectiveContent(input admission.Fragment) (ProspectiveContent, error) {
	if err := admission.CheckFragment(input, admission.RealizationValue); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input.Document())
	if err != nil {
		return nil, err
	}
	parser, err := scenarioParser(DefaultLimits())
	if err != nil {
		return nil, err
	}
	document, err := parser.AdmitProspectiveContent(raw)
	if err != nil {
		return nil, err
	}
	return prospectiveContent{document}, nil
}
