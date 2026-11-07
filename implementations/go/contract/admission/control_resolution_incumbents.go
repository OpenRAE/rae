package admission

import (
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type controlResolutionCrossings struct {
	CrossingContext

	evidence, authority []string
}

func (c controlResolutionCrossings) CrossingEvidenceRefs() []string  { return c.evidence }
func (c controlResolutionCrossings) CrossingAuthorityRefs() []string { return c.authority }

func (r *controlResolution) incumbents(cut any) error {
	context := controlResolutionCrossings{CrossingContext: r.context}
	for _, raw := range r.snapshot.SafeReferences {
		ref, err := r.fragment("ControlArtifactReferenceModel", raw)
		if err != nil {
			return err
		}
		switch stringAt(ref, termKind) {
		case "evidence":
			context.evidence = append(context.evidence, stringAt(ref, "ref"))
		case termAuthority:
			context.authority = append(context.authority, stringAt(ref, "ref"))
		}
	}
	index, err := r.owner.crossingContextIndex(context)
	if err != nil {
		return err
	}
	for _, record := range index.records {
		if err = index.common(record); err != nil {
			return err
		}
		if err = index.stage(record); err != nil {
			return err
		}
	}
	if err = index.transformations(); err != nil {
		return err
	}
	if err = r.crossing(cut, index); err != nil {
		return err
	}
	return r.controlRecords()
}

func (r *controlResolution) crossing(cut any, index *crossingIndex) error {
	record := index.records[stringAt(cut, "crossing", "ref")]
	if record == nil {
		return invalid()
	}
	v := at(record, "occurrence")
	if !equal(at(v, "subject"), at(cut, "subject")) || !equal(at(v, "policy"), at(cut, "policy")) || !matchingFields(v, cut, "direction", "controller_ref") || !equal(at(v, "audience_scope_ref"), at(cut, "audience_ref")) || !set(at(v, termAuthorityBasisRefs))[stringAt(cut, termAuthority, "ref")] {
		return invalid()
	}
	// The reference binds exclude_unset JSON, so hash the original wire record.
	for _, raw := range r.context.CrossingOccurrences() {
		original, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
		if err != nil {
			return err
		}
		if stringAt(original, "event_id") == stringAt(cut, "crossing", "ref") {
			digest, err := jsonDigest(original)
			return require(err == nil && digest == stringAt(cut, "crossing", termDigest))
		}
	}
	return invalid()
}

func (r *controlResolution) controlRecords() error {
	records := r.context.ControlOccurrences()
	if len(records) > 0 {
		v, err := r.owner.contextDocument(termParticipantControlOccurrenceV1, records[0])
		if err != nil {
			return err
		}
		return r.owner.controlOccurrenceV1(validation.Invocation{Instance: v, Context: r.context})
	}
	declarations, targets := r.context.ControlDeclarations(), r.context.ControlTargets()
	if len(declarations) > 4096 || len(targets) > 4096 {
		return invalid()
	}
	index := controlOccurrenceIndex{declarations: map[string]any{}, targets: map[string]any{}}
	return index.authorities(declarations, targets)
}
