package authoring

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// envelopeMembershipView derives values and presence from the same native
// constructor. Presence is never accepted as independently editable authority.
func (p *Parser) envelopeMembershipView(document *Document) (admission.Fragment, map[string][]string, error) { //nolint:ireturn // The shared relation receives only a sealed native fragment.
	if p == nil || p.models == nil || document == nil || !document.Instantiated() {
		return nil, nil, invalid()
	}
	input, err := p.modelValue(document)
	if err != nil {
		return nil, nil, err
	}
	queries := newScopeQueries(p, document.contract, input)
	root := p.schemas[document.contract]
	fill := importDefaultWalk{queries: queries, remaining: compositionJSONWork(p.limits)}
	full, err := fill.value(input, root, "#")
	if err != nil {
		return nil, nil, err
	}
	normal := normalizer{parser: p, id: document.contract, workingLimit: compositionJSONWork(p.limits)}
	constructed, err := normal.walk(root, "#", full, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return nil, nil, err
	}
	data := modelValue(constructed)
	if err = value.Validate(data, value.Runtime()); err != nil {
		return nil, nil, err
	}
	presence := typedPresenceWalk{modelNames: true, queries: queries, presence: map[string][]string{}, defaults: map[string]nodeDefault{}, remaining: value.Runtime().MaxNodes}
	if err = presence.visit(data, root, "#", "", 0); err != nil {
		return nil, nil, err
	}
	aliases := modelProjection{queries: queries, modelNames: true, remaining: value.Runtime().MaxNodes}
	data, err = aliases.project(data, root, "#", 0)
	if err != nil {
		return nil, nil, err
	}
	// The native constructor already returned exact JSON carriers; Marshal is
	// only the bounded external relation projection, not another SDL parse.
	raw, err := json.Marshal(data)
	if err != nil {
		return nil, nil, err
	}
	fragment, err := admission.AdmitFragment(p.models, admission.RealizationValue, data, ingress.Limits{MaxBytes: len(raw), MaxDepth: 64})
	return fragment, presence.presence, err
}

// EnvelopeMembershipDiagnostics checks the admitted instantiated model with
// the shared envelope owner and native typed child presence.
func (p *Parser) EnvelopeMembershipDiagnostics(document *Document, envelope binding.RealizationEnvelopeV1) ([]diagnostic.Diagnostic, error) {
	projection, presence, err := p.envelopeMembershipView(document)
	if err != nil {
		return nil, err
	}
	return admission.RealizationMemberDiagnostics(p.models, envelope, projection, presence)
}
