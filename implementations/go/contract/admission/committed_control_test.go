package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type committedControlFixture struct {
	Record                        json.RawMessage `json:"record"`
	Crossings, Subjects, Policies []json.RawMessage
	AuthorizedEffects             map[string]json.RawMessage                               `json:"authorized_effects"`
	Intents                       map[string]struct{ Evaluation, Outcome json.RawMessage } `json:"intents"`
}

func committedControlOwner(t *testing.T, e *Validator) (any, *controlResolutionTestContext) {
	t.Helper()
	var fixture committedControlFixture
	readFullReferenceJSON(t, "testdata/committed-control-intent.json", &fixture)
	v, c := controlResolutionOwner(t, e, "v2", decodeRuleObject(t, string(fixture.Record)))
	c.crossingTestContext = crossingTestContext{records: flowRawList(fixture.Crossings), subjects: flowRawList(fixture.Subjects), policies: flowRawList(fixture.Policies)}
	c.snapshot.AuthorizedEffects = flowRawMap(fixture.AuthorizedEffects)
	c.snapshot.CommittedIntents = map[string]ControlCommittedIntent{}
	for id, intent := range fixture.Intents {
		c.snapshot.CommittedIntents[id] = ControlCommittedIntent{Evaluation: intent.Evaluation, Outcome: intent.Outcome}
	}
	for _, outcome := range array(at(v, "effect_plan", "effect_outcomes")) {
		c.snapshot.RealizationReceipts[stringAt(outcome, "effect_id")] = controlJSON(t, outcome)
	}
	return v, c
}

func TestCommittedControlIntentRequiresExactOriginAndOwnerOutcome(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	v, c := committedControlOwner(t, e)
	if _, err := e.Validate("participant-control-evaluation-v2", controlJSON(t, v), limits, c); err != nil {
		t.Fatal("independent committed intent:", err)
	}
	for _, name := range []string{"missing", "unreadable-origin", "unreadable-outcome", "foreign-context", "uncommitted", "undispatchable", "unrunnable", "missing-receipt", "changed-outcome", "unrealized"} {
		t.Run(name, func(t *testing.T) {
			v, c := committedControlOwner(t, e)
			alterCommittedControlIntent(t, c, name)
			admitted, err := e.Validate("participant-control-evaluation-v2", controlJSON(t, v), limits, c)
			if err == nil || admitted.ContractID() != "" {
				t.Fatal("substituted committed intent admitted:", err)
			}
		})
	}
}

func alterCommittedControlIntent(t *testing.T, c *controlResolutionTestContext, name string) {
	t.Helper()
	for id, intent := range c.snapshot.CommittedIntents {
		switch name {
		case "missing":
			delete(c.snapshot.CommittedIntents, id)
			continue
		case "unreadable-origin":
			intent.Evaluation = []byte("{")
		case "unreadable-outcome":
			intent.Outcome = []byte("{")
		case "changed-outcome", "unrealized":
			outcome := object(decodeRuleObject(t, string(intent.Outcome)))
			if name == "changed-outcome" {
				outcome["evidence"] = []any{}
			} else {
				outcome["disposition"] = "pending"
			}
			intent.Outcome = controlJSON(t, outcome)
		default:
			intent.Evaluation = alterCommittedOrigin(t, intent.Evaluation, name)
		}
		c.snapshot.CommittedIntents[id] = intent
	}
}

func alterCommittedOrigin(t *testing.T, raw []byte, name string) []byte {
	t.Helper()
	origin := decodeRuleObject(t, string(raw))
	commit := object(at(origin, "commit"))
	switch name {
	case "foreign-context":
		object(at(origin, "request", "context"))["episode_id"] = "foreign"
	case "uncommitted":
		commit["status"] = "prepared"
	case "undispatchable":
		commit["dispatchable_effect_ids"] = []any{}
	case "unrunnable":
		object(at(origin, "effect_plan"))["runnable_effect_ids"] = []any{}
	case "missing-receipt":
		commit["receipt"] = nil
	}
	return controlJSON(t, origin)
}
