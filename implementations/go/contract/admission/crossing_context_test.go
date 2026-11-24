package admission

import (
	"encoding/json"
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type crossingTestContext struct{ records, subjects, policies [][]byte }

func (c crossingTestContext) CrossingOccurrences() [][]byte { return c.records }
func (c crossingTestContext) CrossingSubjects() [][]byte    { return c.subjects }
func (c crossingTestContext) CrossingPolicies() [][]byte    { return c.policies }
func (c crossingTestContext) CrossingEvidenceRefs() []string {
	return []string{"evidence:crossing-1", "evidence-requirement:crossing-decision"}
}
func (c crossingTestContext) CrossingAuthorityRefs() []string { return []string{"authority:red-team"} }

func crossingTestSuccessor(t *testing.T, stage string, order int, prior any) map[string]any {
	t.Helper()
	root := fixtureObject(t, "fixtures/participant-runtime/participant-crossing-occurrence-v1/valid/request.json")
	root["event_id"], root["predecessor_event_refs"] = "crossing."+stage, []any{at(prior, "event_id")}
	v := object(root["occurrence"])
	for _, field := range []string{"request_id", "requested_operation", "action_or_projection_ref", "required_evidence_refs"} {
		delete(v, field)
	}
	v["stage"], v["effective_order"] = stage, json.Number(strconv.Itoa(order))
	return root
}

func TestCrossingDeliveryRequiresItsExactDecisionAttemptAndOwner(t *testing.T) {
	e := boundTestOwner(t)
	request := fixtureObject(t, "fixtures/participant-runtime/participant-crossing-occurrence-v1/valid/request.json")
	decision := crossingTestSuccessor(t, "decided", 11, request)
	d := object(decision["occurrence"])
	d["request_ref"], d["decision_id"], d["decision_revision"], d["disposition"], d["reason_code"], d["required_evidence_refs"] = "crossing-request.1", "decision.1", jsonOne, "permit", "authorized", []any{"evidence-requirement:crossing-decision"}
	gates := map[string]any{}
	for _, gate := range []string{"caller_authorization", "target_authorization", "participant_authority", "action_admission", "visibility", "marking_authorization", "declassification", "backend_support", "transformation_validity"} {
		gates[gate] = "permit"
	}
	d["gates"] = gates
	attempt := crossingTestSuccessor(t, "delivery-attempted", 12, decision)
	a := object(attempt["occurrence"])
	a["decision_ref"], a["attempt_id"], a["owning_occurrence_ref"], a["disposition"] = "decision.1", "attempt.1", at(request, "occurrence", "subject", "subject_ref"), "attempted"
	delivery := crossingTestSuccessor(t, "delivered", 13, attempt)
	v := object(delivery["occurrence"])
	v["decision_ref"], v["attempt_ref"], v["delivery_id"], v["owning_occurrence_ref"], v["delivery_order"], v["disposition"] = "decision.1", "attempt.1", "delivery.1", a["owning_occurrence_ref"], json.Number("13"), "delivered"
	context := crossingTestContext{records: [][]byte{controlJSON(t, request), controlJSON(t, decision), controlJSON(t, attempt), controlJSON(t, delivery)}, subjects: [][]byte{controlJSON(t, at(request, "occurrence", "subject"))}, policies: [][]byte{controlJSON(t, at(request, "occurrence", "policy"))}}
	i := validation.Invocation{Instance: delivery, Context: context}
	if err := validateTestDocument(t, e, "participant-crossing-occurrence-v1", i.Instance, i.Context); err != nil {
		t.Fatal(err)
	}
	a["disposition"] = "failed"
	context.records[2] = controlJSON(t, attempt)
	i.Context = context
	if err := validateTestDocument(t, e, "participant-crossing-occurrence-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted delivery from a failed attempt")
	}
	a["disposition"] = "attempted"
	context.records[2] = controlJSON(t, attempt)
	v["owning_occurrence_ref"] = "foreign.owner"
	context.records[3] = controlJSON(t, delivery)
	i.Context = context
	if err := validateTestDocument(t, e, "participant-crossing-occurrence-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted unrelated delivery owner")
	}
}
