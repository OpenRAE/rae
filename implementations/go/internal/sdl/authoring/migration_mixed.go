package authoring

import (
	"encoding/json"
	"errors"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const mixedMigrationProfile = "convert-mixed-control-finite-script/v1"
const termSourceOrTargetInvalid = "source-or-target-invalid"

type migrationIssue struct{ code, pointer string }

func (p *Parser) migrateMixedControl(data []byte) (*Document, []byte, error) {
	document, err := p.Decode(Request{Source: data})
	if err == nil {
		var admitted *Document
		admitted, _, err = p.Validate(document)
		if err == nil {
			document = admitted
		}
	}
	var output *Document
	issues, affected := []migrationIssue{}, []string{}
	if err == nil {
		output, issues, affected, err = p.convertMixedDocument(document)
	}
	if err != nil {
		issues = mixedValidationIssues(err)
		output = nil
	}
	if output == nil {
		affected = []string{}
	}
	slices.SortFunc(issues, func(a, b migrationIssue) int {
		if order := strings.Compare(a.code, b.code); order != 0 {
			return order
		}
		return strings.Compare(a.pointer, b.pointer)
	})
	diagnostics := []any{}
	for _, issue := range slices.Compact(issues) {
		diagnostics = append(diagnostics, operationDiagnostic("mixed-control-migration."+issue.code, "Mixed-control conversion refused; see docs/migration/mixed-control-finite-script-conversion.md.", issue.pointer, termError))
	}
	slices.Sort(affected)
	policyDigest, err := jsonIdentity(nil)
	if err != nil {
		return nil, nil, err
	}
	profile := migrationReportProfile{operation: mixedMigrationProfile, source: "sdl-mixed-control/fixed-coordinate-v1", canonical: "mixed-control-migration-digest-pair/v1", preservation: "legacy-mixed-control-trace-constraints/v1", precondition: "legacy-trace-constraints-preserved", postcondition: "rev1-target-admitted", limitations: []string{"Conversion preserves authored trace constraints; it is not evidence of an executed or equivalent runtime trace.", "Legacy proposal_revision values equal state revisions; converted proposals and decisions bind revision 1."}}
	report, err := simpleMigrationReport(data, output, profile, policyDigest, slices.Compact(affected), diagnostics)
	if err != nil {
		return nil, nil, err
	}
	return p.operationResult(output, report, nil)
}

func (p *Parser) convertMixedDocument(document *Document) (*Document, []migrationIssue, []string, error) {
	value, err := ingress.Parse(document.JSON(), modelLimits(document.data), ingress.Object)
	if err != nil {
		return nil, nil, nil, err
	}
	payload := object(value)
	composer := composition{parser: p}
	full, err := composer.bindingPayload(payload, nil)
	if err != nil {
		return nil, nil, nil, err
	}
	issues, affected := []migrationIssue{}, []string{}
	for _, row := range document.semantic.behaviors {
		if row.mixed == nil || row.mixed.Semantics == reusableMixedSemantics {
			continue
		}
		policy := object(object(object(full[behaviorSection])[row.name])[termMixedControl])
		var declaration semanticMixed
		encoded, encodingErr := json.Marshal(policy)
		if encodingErr != nil || json.Unmarshal(encoded, &declaration) != nil {
			return nil, nil, nil, invalid()
		}
		issues = append(issues, mixedTransitionIssues(row.name, declaration)...)
		issues = append(issues, mixedDeliveryIssues(row, declaration)...)
		affected = append(affected, mixedRevisionPointers(row.name, policy)...)

		object(object(payload[behaviorSection])[row.name])[termMixedControl] = convertedMixedPolicy(policy, declaration)
	}
	if len(issues) > 0 {
		return nil, issues, affected, nil
	}
	output, err := p.admitMigrationPayload(payload)
	if err == nil {
		_, err = output.CanonicalDigest()
	}
	return output, issues, affected, err
}

func mixedRevisionPointers(name string, policy map[string]any) []string {
	affected := []string{}
	for id, raw := range object(policy["transitions"]) {
		if object(raw)["proposal_revision"] != nil {
			affected = append(affected, mixedTransitionPointer(name, id)+"/proposal_revision")
		}
	}
	return affected
}
func orderedMixedTransitions(policy semanticMixed) []string {
	ids := slices.Sorted(maps.Keys(policy.Transitions))
	slices.SortStableFunc(ids, func(a, b string) int {
		left, right := policy.Transitions[a].Effective, policy.Transitions[b].Effective
		if modelLess(left, right) {
			return -1
		}
		if modelLess(right, left) {
			return 1
		}
		return 0
	})
	return ids
}
func mixedTransitionPointer(spec, transition string) string {
	return jsonpointer.FromTokens([]string{behaviorSection, spec, termMixedControl, "transitions", transition})
}
func mixedTransitionIssues(spec string, policy semanticMixed) []migrationIssue {
	issues := []migrationIssue{}
	established := map[string]bool{}
	for _, id := range orderedMixedTransitions(policy) {
		transition := policy.Transitions[id]
		pointer := mixedTransitionPointer(spec, id)
		changes := resolvedControllerReference(policy.States[transition.Source].Controller, policy.Participant) != resolvedControllerReference(policy.States[transition.Target].Controller, policy.Participant)
		rules := []struct {
			applies bool
			code    string
		}{
			{transition.Kind == handoffTerm && !changes, "handoff-without-controller-change"},
			{transition.Kind != handoffTerm && changes, "controller-change-requires-handoff"},
			{transition.Proposal != nil && slices.Contains([]string{"intervention", handoffTerm, "override"}, transition.Kind), "proposal-target-outside-kind-set"},
			{len(transition.Completion) > 0 && transition.Kind != handoffTerm, termSourceOrTargetInvalid},
		}
		for _, rule := range rules {
			if rule.applies {
				issues = append(issues, migrationIssue{rule.code, pointer})
			}
		}
		coordinate := transition.Source + "\x00" + transition.Expected.String()
		if established[coordinate] {
			issues = append(issues, migrationIssue{"branching-sequence", pointer})
		}
		established[coordinate] = true
	}
	return issues
}
func mixedDeliveryIssues(row semanticBehavior, policy semanticMixed) []migrationIssue {
	issues := []migrationIssue{}
	for _, delivery := range row.deliveries {
		if delivery.Transition == nil {
			continue
		}
		transition, present := policy.Transitions[*delivery.Transition]
		if !present {
			continue
		}
		pointer := jsonpointer.FromTokens([]string{behaviorSection, row.name, participantInjectDeliveriesField, delivery.id})
		issues = append(issues, migrationIssue{"order-time-mapping-required", pointer}, migrationIssue{"policy-revision-conflated", pointer})
		from, to := policy.States[transition.Source], policy.States[transition.Target]
		if resolvedControllerReference(from.Controller, policy.Participant) != resolvedControllerReference(to.Controller, policy.Participant) || !equalStringSet(from.Scope, to.Scope) {
			issues = append(issues, migrationIssue{"source-destination-authority-disagreement", pointer})
		}
	}
	return issues
}
func equalStringSet(a, b []string) bool {
	left, right := slices.Clone(a), slices.Clone(b)
	slices.Sort(left)
	slices.Sort(right)
	return slices.Equal(slices.Compact(left), slices.Compact(right))
}

func convertedMixedPolicy(raw map[string]any, policy semanticMixed) map[string]any {
	converted := map[string]any{"semantics": reusableMixedSemantics, "form": "finite-script"}
	for _, field := range []string{termParticipantRef, "policy_revision", "order_strategy", "initial_state_ref", "dispositions", "controller_states"} {
		converted[field] = raw[field]
	}
	edges, steps := map[string]any{}, []any{}
	for _, id := range orderedMixedTransitions(policy) {
		transition, source := policy.Transitions[id], object(object(raw["transitions"])[id])
		edge := map[string]any{}
		for _, field := range []string{"transition_kind", "from_state_ref", "to_state_ref", "valid_from_order", "valid_until_order", "evidence_refs"} {
			edge[field] = source[field]
		}
		if transition.Kind == handoffTerm {
			edge["completion_evidence_refs"] = source["completion_evidence_refs"]
		}
		if transition.Kind == "external-direction" {
			edge["target_kinds"] = []any{proposalTerm}
		}
		edges[id] = edge
		step := map[string]any{"step_id": id, "permitted_transition_ref": id, "expected_state_revision": source["expected_state_revision"], "valid_from_order": source["effective_order"], "valid_until_order": source["effective_order"]}
		if transition.Proposal != nil {
			step["target_step_ref"] = *transition.Proposal
			if transition.Kind == "cancellation" {
				step["target_kind"] = proposalTerm
			}
		}
		steps = append(steps, step)
	}
	converted["permitted_transitions"], converted["script_steps"] = edges, steps
	return converted
}

// Only the semantic owner's explicit transition pointer is transported.
// Diagnostic prose and authored reference strings have no location authority.
func mixedValidationIssues(err error) []migrationIssue {
	semantic, ok := errors.AsType[*semanticError](err)
	if !ok {
		return []migrationIssue{{termSourceOrTargetInvalid, ""}}
	}
	issues := []migrationIssue{}
	for _, finding := range semantic.findings {
		pointer := ""
		tokens := jsonpointer.Tokens(finding.Pointer)
		if len(tokens) == 5 && tokens[0] == behaviorSection && tokens[2] == termMixedControl && slices.Contains([]string{"transitions", "permitted_transitions"}, tokens[3]) {
			pointer = mixedTransitionPointer(tokens[1], tokens[4])
		}
		issues = append(issues, migrationIssue{termSourceOrTargetInvalid, pointer})
	}
	return issues
}
