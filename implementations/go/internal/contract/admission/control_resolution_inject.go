package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/ingress"

func (r *controlResolution) inject(target, cut any) error {
	owner, ok := r.snapshot.InjectOwners[stringAt(target, "delivery_ref", "ref")]
	if !ok || owner.Digest != stringAt(target, "delivery_ref", termDigest) {
		return invalid()
	}
	if owner.Controlled {
		return r.controlledInject(target, cut, owner)
	}
	if len(owner.Coordinates) > 0 {
		canonical, err := r.fragment("ControlInjectEffectModel", owner.Coordinates)
		return require(err == nil && equal(canonical, target) && equal(at(target, "episode_id"), at(cut, "episode_id")) && owner.AudienceScopeRef == stringAt(cut, "audience_ref"))
	}
	observed := map[string]any{
		"participant_address": owner.ParticipantAddress, "inject_ref": owner.InjectRef,
		"event_ref": owner.EventRef, "script_ref": owner.ScriptRef, "story_ref": owner.StoryRef,
		"source_item_ref": owner.SourceItemRef, "result_item_ref": owner.ResultItemRef,
	}
	return require(matchingFields(target, observed, "participant_address", "inject_ref", "event_ref", "script_ref", "story_ref", "source_item_ref", "result_item_ref") && owner.DisclosureRef == stringAt(target, "disclosure_ref", "ref") && equal(at(target, "episode_id"), at(cut, "episode_id")) && owner.AudienceScopeRef == stringAt(cut, "audience_ref"))
}

func (r *controlResolution) controlledInject(target, cut any, owner ControlInjectOwner) error {
	canonical, err := r.fragment("ControlInjectEffectModel", owner.Coordinates)
	if err != nil || !equal(canonical, target) || owner.Application.ContractID() != "participant-inject-delivery-v1" {
		return invalid()
	}
	v, err := ingress.Parse(owner.Application.JSON(), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return err
	}
	if at(v, "application", "control") == nil {
		return invalid()
	}
	return require(equal(at(v, "application", "delivery_address"), at(target, "delivery_ref", "ref")) && equal(at(v, "application", "delivery_digest"), at(target, "delivery_ref", termDigest)) && equal(at(v, "participant_address"), at(target, "participant_address")) && equal(at(v, "episode_id"), at(cut, "episode_id")) && equal(at(v, "disclosed_item", termArtifactID), at(target, "result_item_ref")) && equal(at(v, "visibility_projection_ref"), at(target, "disclosure_ref", "ref")))
}
