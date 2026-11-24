package authoring

import (
	"regexp"
	"slices"
	"strings"
)

var variableTokens = regexp.MustCompile(`\$\{((?:(?:[a-z0-9][a-z0-9_-]{0,63}|__private)\.)*[a-z0-9][a-z0-9_-]{0,63})\}`)

type referenceFields struct{ path, fields []string }

func authoredReferenceFields() []referenceFields {
	return []referenceFields{
		{[]string{behaviorSection, "*"}, []string{participantRefsField, actionRefsField, boundaryRefsField, outcomeRefsField, authorityScopeRefsField}},
		{[]string{agentsSection, "*"}, []string{"affiliations", termActions, boundariesSection, "starting_accounts", "allowed_subnets", "starting_assertions", "authority_anchors", "operating_scope"}},
		{[]string{agentsSection, "*", "initial_knowledge"}, []string{"hosts", "subnets", servicesField, accountsSection}},
		{[]string{agentsSection, "*", "interactive_access", "*"}, []string{"target_ref", "account_ref"}},
		{[]string{agentsSection, "*", controlContextField, "*"}, []string{declarationRefField}},
		{[]string{behaviorSection, "*", controlContextField, "*"}, []string{declarationRefField}},
		{[]string{behaviorSection, "*", toolAffordancesField, "*"}, []string{participantRefsField, actionRefsField, boundaryRefsField, toolRefField}},
		{[]string{behaviorSection, "*", participantInjectDeliveriesField, "*"}, []string{termParticipantRef, "inject_ref", "observation_boundary_ref", "source_item_ref", "result_item_ref", "controller_ref", "temporal_constraint_refs", evidenceRequirementRefsField, "control_authority_scope_refs", "control_evidence_refs"}},
		{[]string{behaviorSection, "*", participantInjectDeliveriesField, "*", "occurrence"}, []string{"event_ref", "script_ref", "story_ref"}},
	}
}
func authoredReferences(value, generated any) error {
	for _, rule := range authoredReferenceFields() {
		if err := referenceRecords(value, generated, rule.path, rule.fields); err != nil {
			return err
		}
	}
	return nil
}
func referenceRecords(value, generated any, path, fields []string) error {
	current, baseline := object(value), object(generated)
	if len(path) == 0 {
		for _, name := range fields {
			if !privateReferenceAllowed(current[name], baseline[name]) {
				return invalid()
			}
		}
		return nil
	}
	if path[0] != "*" {
		return referenceRecords(current[path[0]], baseline[path[0]], path[1:], fields)
	}
	for key, child := range current {
		if err := referenceRecords(child, baseline[key], path[1:], fields); err != nil {
			return err
		}
	}
	return nil
}
func privateReferenceAllowed(value, baseline any) bool {
	switch v := value.(type) {
	case string:
		return !slices.Contains(strings.Split(v, "."), privateSegment) || v == baseline
	case []any:
		previous := array(baseline)
		for i, child := range v {
			var generated any
			if i < len(previous) {
				generated = previous[i]
			}
			if !privateReferenceAllowed(child, generated) {
				return false
			}
		}
	}
	return true
}
func containsVariable(value any) bool {
	switch v := value.(type) {
	case string:
		return variableTokens.MatchString(v)
	case []any:
		return slices.ContainsFunc(v, containsVariable)
	case ordered:
		return slices.ContainsFunc(v, func(item field) bool { return containsVariable(item.value) })
	case map[string]any:
		for _, child := range v {
			if containsVariable(child) {
				return true
			}
		}
	}
	return false
}
