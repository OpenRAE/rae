package authoring

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
)

func conceptSubjects(document *Document, digest string) []concept.Subject {
	phase := "normalized-authoring"
	if document.contract == expandedContract {
		phase = "expanded-authoring"
	}
	result := []concept.Subject{}
	for _, address := range slices.Sorted(maps.Keys(document.semantic.index.declarations)) {
		declaration := document.semantic.index.declarations[address]
		result = append(result, concept.Subject{SubjectKind: declaration.collisionKind, OwningContractID: authoringContract, LifecyclePhase: phase, CanonicalRef: address, ArtifactDigest: digest})
	}
	for node, raw := range object(document.semantic.root[nodesSection]) {
		for _, rawApplication := range array(object(object(raw)["runtime"])["applications"]) {
			application := object(rawApplication)
			id := text(application["application_id"])
			if containsVariable(id) {
				continue
			}
			for _, rawRoute := range array(application["routes"]) {
				route := text(object(rawRoute)["route_id"])
				if containsVariable(route) {
					continue
				}
				result = append(result, concept.Subject{SubjectKind: "runtime-application-route", OwningContractID: authoringContract, LifecyclePhase: phase, CanonicalRef: termNodesPrefix + node + ".runtime.applications." + id + ".routes." + route, ArtifactDigest: digest})
			}
		}
	}
	return result
}
func (t *transformation) retargetBindings(target *Document) ([]any, error) {
	targetDigest, err := target.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	from := conceptSubjects(t.source, t.sourceDigest)
	into := conceptSubjects(target, targetDigest)
	change := bindingRetarget{from: from, into: into, sourceDigest: t.sourceDigest, targetDigest: targetDigest, before: t.request.Request.Target, after: t.after}
	return t.parser.retargetBindingDocuments(change, t.request.Bindings, t.parser.authority.PinnedSnapshots(), false)
}

type bindingTransport struct {
	from, into                                map[string]concept.Subject
	sourceDigest, targetDigest, before, after string
}

type bindingRetarget struct {
	from, into                                []concept.Subject
	sourceDigest, targetDigest, before, after string
}

func (p *Parser) retargetBindingDocuments(change bindingRetarget, documents []json.RawMessage, snapshots []concept.SchemeSnapshot, resolveAll bool) ([]any, error) {
	transport := bindingTransport{from: map[string]concept.Subject{}, into: map[string]concept.Subject{}, sourceDigest: change.sourceDigest, targetDigest: change.targetDigest, before: change.before, after: change.after}
	for _, subject := range change.from {
		transport.from[subject.CanonicalRef] = subject
	}
	for _, subject := range change.into {
		transport.into[subject.CanonicalRef] = subject
	}
	result := []any{}
	for _, raw := range documents {
		payload, err := p.retargetBindingDocument(raw, transport, change.into, snapshots, resolveAll)
		if err != nil {
			return nil, err
		}
		result = append(result, payload)
	}
	return result, nil
}
func (p *Parser) retargetBindingDocument(raw []byte, transport bindingTransport, subjects []concept.Subject, snapshots []concept.SchemeSnapshot, resolveAll bool) (map[string]any, error) {
	admitted, err := p.models.Validate(termExternalConceptBindingsV1, raw, modelLimits(raw), nil)
	if err != nil {
		return nil, err
	}
	decoded, err := ingress.Parse(admitted.JSON(), modelLimits(raw), ingress.Object)
	if err != nil {
		return nil, err
	}
	payload := object(decoded)
	owned := map[string]any{}
	for id, rawBinding := range object(payload[termBindings]) {
		binding := object(rawBinding)
		changed, transportErr := transport.retarget(binding)
		if transportErr != nil {
			return nil, transportErr
		}
		if changed {
			owned[id] = binding
		}
	}
	if resolveAll {
		owned = object(payload[termBindings])
	}
	if len(owned) > 0 || resolveAll {
		current := maps.Clone(payload)
		current[termBindings] = owned
		if err = p.admitTransportedBindings(current, subjects, snapshots); err != nil {
			return nil, err
		}
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	if err = p.models.CheckPortable(termExternalConceptBindingsV1, encoded, modelLimits(encoded)); err != nil {
		return nil, err
	}
	return payload, nil
}
func (b bindingTransport) retarget(binding map[string]any) (bool, error) {
	subject := object(binding["subject"])
	canonical := text(subject["canonical_ref"])
	source, exists := b.from[canonical]
	sameCoordinate := exists && source.SubjectKind == subject["subject_kind"] && source.OwningContractID == subject["owning_contract_id"] && source.LifecyclePhase == subject["lifecycle_phase"]
	sameDigest := strings.EqualFold(b.sourceDigest, text(subject["artifact_digest"]))
	if sameCoordinate && !sameDigest || sameDigest && !sameCoordinate {
		return false, invalid()
	}
	if !sameDigest {
		return false, nil
	}
	if canonical == b.before {
		canonical = b.after
	}
	current, known := b.into[canonical]
	if !known || current.SubjectKind != source.SubjectKind {
		return false, invalid()
	}
	subject["canonical_ref"], subject["artifact_digest"] = canonical, b.targetDigest
	return true, nil
}
func (p *Parser) admitTransportedBindings(payload map[string]any, subjects []concept.Subject, snapshots []concept.SchemeSnapshot) error {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	value, err := p.models.Validate(termExternalConceptBindingsV1, encoded, modelLimits(encoded), nil)
	if err != nil {
		return err
	}
	resolution, err := p.authority.AdmitBindings(subjects, value, snapshots)
	if err != nil || !resolution.Admitted() {
		return invalid()
	}
	return nil
}
