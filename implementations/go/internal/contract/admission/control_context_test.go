package admission

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type controlAgreementTestContext struct {
	snapshot                            ControlSnapshot
	assets, selections, surfaces, views [][]byte
	allow                               bool
	failure                             error
	requests                            []ControlAuthorityRequest
}

func (c *controlAgreementTestContext) ControlSnapshot() ControlSnapshot { return c.snapshot }
func (c *controlAgreementTestContext) ControlAssets() [][]byte          { return c.assets }
func (c *controlAgreementTestContext) ControlSelections() [][]byte      { return c.selections }
func (c *controlAgreementTestContext) ControlSurfaces() [][]byte        { return c.surfaces }
func (c *controlAgreementTestContext) ControlViews() [][]byte           { return c.views }
func (c *controlAgreementTestContext) AuthorizeControl(request ControlAuthorityRequest) (bool, error) {
	c.requests = append(c.requests, request)
	return c.allow, c.failure
}
func (c *controlAgreementTestContext) ControlCutPrecedes(_, _ json.RawMessage) (bool, error) {
	return c.allow, c.failure
}

func TestControlContextTrustedSelectionAndLifecycle(t *testing.T) {
	e := boundTestOwner(t)
	v := fixtureObject(t, "fixtures/participant-runtime/participant-control-context-record-v1/valid/selected-blue.json")
	asset := fixtureObject(t, "fixtures/participant-runtime/participant-control-context-asset-v1/valid/instruction.json")
	assetRaw, err := json.Marshal(asset)
	if err != nil {
		t.Fatal(err)
	}
	cutRaw, err := json.Marshal(v["record_cut"])
	if err != nil {
		t.Fatal(err)
	}
	context := &controlAgreementTestContext{snapshot: ControlSnapshot{ScopeRef: stringAt(v, "scope_ref"), RunID: stringAt(v, "run_id"), ParticipantAddress: stringAt(v, "participant_address"), EpisodeID: stringAt(v, "episode_id"), AudienceScopeRef: stringAt(v, "audience_scope_ref"), EpisodeGeneration: jsonZero, RecordCut: cutRaw, Lifecycle: map[[3]string]string{{"privacy-instruction", "one", "cuts.0"}: "active"}, Roles: map[string][]string{"cuts.0": {"roles.analyst"}}}, assets: [][]byte{assetRaw}, allow: true}
	i := validation.Invocation{Key: validation.Key{ContractID: "participant-control-context-record-v1"}, Instance: v, Context: context}
	if err := e.controlContextAgreement(i); err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, i.Key.ContractID, i.Instance, i.Context); err != nil {
		t.Fatal(err)
	}
	if len(context.requests) != 2 || context.requests[0].Operation != "select" || context.requests[0].Snapshot.ParticipantAddress != "participants.blue" {
		t.Fatal("incomplete authority coordinates")
	}
	context.allow = false
	if err := validateTestDocument(t, e, i.Key.ContractID, i.Instance, i.Context); err == nil {
		t.Fatal("full admission accepted denied authority")
	}
	if err := e.controlContextAgreement(i); err == nil {
		t.Error("accepted denied selection")
	}
	context.allow = true
	context.snapshot.Roles = nil
	if err := e.controlContextAgreement(i); err == nil {
		t.Error("accepted selection outside applicability")
	}
	context.snapshot.Roles = map[string][]string{"cuts.0": {"roles.analyst"}}
	context.snapshot.Lifecycle[[3]string{"privacy-instruction", "one", "cuts.0"}] = "withdrawn"
	if err := e.controlContextAgreement(i); err == nil {
		t.Error("accepted withdrawn asset")
	}
	change := fixtureObject(t, "fixtures/participant-runtime/participant-control-context-change-v1/valid/publish.json")
	i.Key.ContractID = "participant-control-context-change-v1"
	i.Instance = change
	context.snapshot.Lifecycle[[3]string{"privacy-instruction", "one", "cuts.0"}] = "unpublished"
	if err := e.controlContextAgreement(i); err != nil {
		t.Fatal(err)
	}
	context.failure = errors.New("private-authority-error")
	if err := e.controlContextAgreement(i); err == nil {
		t.Error("accepted resolver failure")
	} else if category, ok := fault.CategoryOf(err); !ok || category != fault.Operational {
		t.Errorf("failure category=%v", err)
	}
}

func controlJSON(t *testing.T, v any) []byte {
	t.Helper()
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestControlContextDisclosureAndDeliveryResolveExactSources(t *testing.T) {
	e := boundTestOwner(t)
	v, context, surface, view, binding := controlDisclosureFixture(t)
	i := validation.Invocation{Key: validation.Key{ContractID: "participant-control-context-record-v1"}, Instance: v, Context: context}
	if err := e.controlContextAgreement(i); err != nil {
		t.Fatal(err)
	}
	ops := []string{}
	for _, request := range context.requests {
		ops = append(ops, request.Operation)
	}
	if !equal(ops, []string{"select", "disclose", "disclose", "deliver"}) {
		t.Errorf("authorities=%v", ops)
	}
	view["payload_ref"] = "context.unrelated"
	context.views = [][]byte{controlJSON(t, view)}
	if err := e.controlContextAgreement(i); err == nil {
		t.Error("accepted unrelated context view")
	}
	view["payload_ref"] = at(binding, "item_ref")
	context.views = [][]byte{controlJSON(t, view)}
	object(surface["delivery"])["delivery_cut_ref"] = "cuts.other"
	context.surfaces = [][]byte{controlJSON(t, surface)}
	if err := e.controlContextAgreement(i); err == nil {
		t.Error("accepted mismatched delivery cut")
	}
}

func controlDisclosureFixture(t *testing.T) (map[string]any, *controlAgreementTestContext, map[string]any, map[string]any, map[string]any) {
	t.Helper()
	v := fixtureObject(t, "fixtures/participant-runtime/participant-control-context-record-v1/valid/delivered.json")
	selected := fixtureObject(t, "fixtures/participant-runtime/participant-control-context-record-v1/valid/selected-red.json")
	asset := fixtureObject(t, "fixtures/participant-runtime/participant-control-context-asset-v1/valid/instruction.json")
	surface := fixtureObject(t, "fixtures/control-plane/participant-decision-surface-v2/valid/delivered-initial.json")
	binding := object(array(at(surface, "assurance", "exposure_bindings"))[0])
	binding["source_ref"] = "urn:" + stringAt(v, "asset_ref", "asset_digest")
	binding["transformation_rule_ref"], binding["source_layer_ref"] = "transformations.redacted-instruction", "source.instruction"
	object(surface["delivery"])["delivery_cut_ref"] = "cuts.2"
	view := fixtureObject(t, "fixtures/control-plane/participant-context-view-v1/valid/network-posture-context.json")
	view["participant_address"], view["episode_id"], view["view_ref"], view["payload_ref"] = "participants.red", "episode-1", at(surface, "participant_view", "context_view_ref"), at(binding, "item_ref")
	view["visibility_projection_ref"], view["redaction_policy_ref"], view["marking_definition_refs"] = at(surface, "assurance", "visibility_projection_ref"), at(surface, "participant_view", "redaction_policy_ref"), at(surface, "participant_view", "marking_definition_refs")
	view["derived_from_refs"] = []any{binding["source_ref"]}
	view["source_layers"] = []any{map[string]any{"source_id": "source.instruction", "source_layer": "participant_control_context_asset", "ref": binding["source_ref"], "temporal_relation": "same_observation_point", "evidence_refs": []any{"evidence.asset"}, "provenance_refs": []any{"provenance.asset"}}}
	object(view["transformation"])["input_source_ids"] = []any{"source.instruction"}
	object(view["transformation"])["transformation_rule_ref"] = binding["transformation_rule_ref"]
	context := &controlAgreementTestContext{snapshot: ControlSnapshot{ScopeRef: stringAt(v, "scope_ref"), RunID: stringAt(v, "run_id"), ParticipantAddress: "participants.red", EpisodeID: "episode-1", AudienceScopeRef: stringAt(v, "audience_scope_ref"), EpisodeGeneration: jsonZero, RecordCut: controlJSON(t, v["record_cut"]), Lifecycle: map[[3]string]string{}, Roles: map[string][]string{"cuts.0": {"roles.analyst"}}}, assets: [][]byte{controlJSON(t, asset)}, selections: [][]byte{controlJSON(t, selected)}, surfaces: [][]byte{controlJSON(t, surface)}, views: [][]byte{controlJSON(t, view)}, allow: true}
	for _, cut := range []string{"cuts.0", "cuts.2", stringAt(surface, "assurance", "derivation_anchor", "state_cut", "cut_ref")} {
		context.snapshot.Lifecycle[[3]string{"privacy-instruction", "one", cut}] = "active"
	}
	return v, context, surface, view, binding
}
