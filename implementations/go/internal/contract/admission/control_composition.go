package admission

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func controlEvaluationV1(v any) error {
	request := at(v, "request")
	if err := controlRequest(request, false); err != nil {
		return err
	}
	blockers, err := controlEffectBlockers(request, array(at(v, "results")), array(at(v, "realizations")))
	if err != nil {
		return err
	}
	if err := controlResultBlockers(request, array(at(v, "results")), blockers); err != nil {
		return err
	}
	if err := controlSupportBlockers(request, array(at(v, "support")), blockers); err != nil {
		return err
	}
	gate := stringAt(v, "composition", "incumbent_gate_disposition")
	if gate != termPermit {
		blockers["incumbent-gates"] = true
	}
	if !equal(stringsOf(at(v, "composition", "contributing_result_ids")), controlContributors(array(at(v, "results")))) || !sortedUnique(stringsOf(at(v, "composition", "blockers"))) || !equalSet(blockers, set(at(v, "composition", "blockers"))) {
		return invalid()
	}
	return require(stringAt(v, "composition", "disposition") == controlCompositionDisposition(v, blockers, gate))
}

func controlRows(rows any, identity string) map[string]any {
	indexed := map[string]any{}
	for _, row := range array(rows) {
		indexed[stringAt(row, identity)] = row
	}
	return indexed
}

func controlContributors(results []any) []string {
	ordered := slices.Clone(results)
	slices.SortFunc(ordered, func(a, b any) int {
		if value := strings.Compare(stringAt(a, "instance_id"), stringAt(b, "instance_id")); value != 0 {
			return value
		}
		return strings.Compare(stringAt(a, "slot_id"), stringAt(b, "slot_id"))
	})
	return rowIDs(ordered, "result_id")
}

func controlResultBlockers(request any, results []any, blockers map[string]bool) error {
	selection := at(request, "selection")
	bindings, slots := controlRows(at(selection, termBindings), "instance_id"), controlRows(at(selection, "slots"), "slot_id")
	index := controlRows(results, "slot_id")
	if len(index) != len(results) || len(rowSet(results, "result_id")) != len(results) || !sameKeys(slots, keySet(index)) {
		return invalid()
	}
	contextDigest, err := controlDigest(at(request, "context"))
	if err != nil {
		return err
	}
	edges := map[string][]string{}
	for id, result := range index {
		slot := slots[id]
		binding := bindings[stringAt(slot, "instance_id")]
		if err = controlResultBinding(result, slot, binding, at(request, "context"), contextDigest); err != nil {
			return err
		}
		edges[id] = rowIDs(at(slot, "dependencies"), "slot_id")
	}
	if graph.HasCycle(edges) {
		return invalid()
	}
	order, err := graph.Order(edges, nil)
	if err != nil {
		return invalid()
	}
	satisfied := controlSatisfiedSlots(order, edges, index)
	controlMandatoryBlockers(slots, index, edges, satisfied, blockers)
	return nil
}

func controlResultBinding(result, slot, binding, context any, contextDigest string) error {
	commitment, err := controlDigest(binding)
	if err != nil {
		return err
	}
	if !equal(at(result, "instance_id"), at(slot, "instance_id")) || stringAt(result, "binding_digest") != commitment || stringAt(result, "context_digest") != contextDigest || at(result, "payload") != nil && !equal(at(result, "payload", termKind), at(slot, termKind)) {
		return invalid()
	}
	return controlIFCResult(result, binding, context)
}

func controlIFCResult(result, binding, context any) error {
	payload := at(result, "payload")
	if stringAt(payload, termKind) != termIfcFact {
		return nil
	}
	expected := map[string]string{"teaching-influence-domain/rev1": termTeachingInfluence, "sem-233/rev1": termParticipantBoundaryFlowPolicyV1, termOwnerIfcRev1: termParticipantOwnerFlowPolicyV1}[stringAt(payload, "domain")]
	if !rowSet(at(binding, "profiles"), "ref")[expected] {
		return invalid()
	}
	if expected == termParticipantOwnerFlowPolicyV1 {
		found := false
		for _, profile := range array(at(binding, "profiles")) {
			found = found || equal(profile, at(payload, "profile"))
		}
		if !found {
			return invalid()
		}
	}
	if expected == termTeachingInfluence {
		return require(equalSet(rowTupleSet(at(payload, "source_refs"), termKind, "ref", termRevision, termDigest), rowTupleSet(at(context, "inputs"), termKind, "ref", termRevision, termDigest)))
	}
	return nil
}

func controlResultSatisfied(v any) bool {
	return stringAt(v, "status") == termResolved && (stringAt(v, "payload", termKind) != termDecision || stringAt(v, "payload", "disposition") == termPermit)
}

func controlSupportBlockers(request any, support []any, blockers map[string]bool) error {
	if len(rowSet(support, "instance_id")) != len(support) || !equalSet(rowSet(support, "instance_id"), rowSet(at(request, "selection", termBindings), "instance_id")) {
		return invalid()
	}
	digest, err := controlDigest(at(request, "context"))
	if err != nil {
		return err
	}
	for _, item := range support {
		if stringAt(item, "context_digest") != digest {
			return invalid()
		}
		if stringAt(item, "status") != termResolved || stringAt(item, "effective_level") != postureExact {
			blockers["support:"+stringAt(item, "instance_id")] = true
		}
	}
	return nil
}

func controlCompositionDisposition(v any, blockers map[string]bool, gate string) string {
	if len(blockers) == 0 {
		return termEligible
	}
	causes := map[string]bool{}
	for blocker := range blockers {
		prefix, identity, _ := strings.Cut(blocker, ":")
		switch prefix {
		case "slot", "dependency":
			controlSlotCauses(at(v, "request", "selection"), array(at(v, "results")), identity, causes)
		case "support":
			causes[controlSupportCause(controlRows(at(v, "support"), "instance_id")[identity])] = true
		case "predecessor":
			causes[termWithhold] = true
		case reasonEffectConflict:
			causes["conflict"] = true
		case "incumbent-gates":
			causes[controlUnsatisfiedStatus(gate)] = true
		}
	}
	for _, cause := range []string{"conflict", termStale, statusUnsupported, termWeakened, termDeny, termWithhold, outcomeFailed} {
		if causes[cause] {
			return cause
		}
	}
	return outcomeFailed
}

func controlUnsatisfiedStatus(status string) string {
	if status == "missing" || status == statusUnknown {
		return outcomeFailed
	}
	return status
}

func controlSupportCause(v any) string {
	if stringAt(v, "effective_level") == statusUnsupported {
		return statusUnsupported
	}
	if stringAt(v, "status") != termResolved {
		return controlUnsatisfiedStatus(stringAt(v, "status"))
	}
	return termWeakened
}

func controlSlotCauses(selection any, results []any, id string, causes map[string]bool) {
	slots, index := controlRows(at(selection, "slots"), "slot_id"), controlRows(results, "slot_id")
	pending, seen := []string{id}, map[string]bool{}
	for len(pending) > 0 {
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if seen[current] {
			continue
		}
		seen[current] = true
		result := index[current]
		if stringAt(result, "status") != termResolved {
			causes[controlUnsatisfiedStatus(stringAt(result, "status"))] = true
		} else if stringAt(result, "payload", termKind) == termDecision {
			disposition := stringAt(result, "payload", "disposition")
			if disposition != termPermit {
				if disposition != termDeny && disposition != termWithhold {
					disposition = outcomeFailed
				}
				causes[disposition] = true
			}
		}
		pending = append(pending, rowIDs(at(slots[current], "dependencies"), "slot_id")...)
	}
}

func controlSatisfiedSlots(order []string, edges map[string][]string, index map[string]any) map[string]bool {
	satisfied := map[string]bool{}
	for _, id := range order {
		satisfied[id] = controlResultSatisfied(index[id])
		for _, dependency := range edges[id] {
			satisfied[id] = satisfied[id] && satisfied[dependency]
		}
	}
	return satisfied
}
func controlMandatoryBlockers(slots, index map[string]any, edges map[string][]string, satisfied, blockers map[string]bool) {
	for id, slot := range slots {
		if stringAt(slot, "role") == "mandatory" {
			if !controlResultSatisfied(index[id]) {
				blockers["slot:"+id] = true
			}
			for _, dependency := range edges[id] {
				if !satisfied[dependency] {
					blockers["dependency:"+id] = true
				}
			}
		}
	}
}
