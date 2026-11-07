package admission

func (s *controlAgreement) record(v any) error {
	if err := s.selection(v); err != nil {
		return err
	}
	if err := s.selectionHistory(v); err != nil {
		return err
	}
	switch stringAt(v, "disposition") {
	case termSelected:
		return require(equal(at(v, "record_cut"), at(v, "selection_cut")))
	case termWithheld:
		if at(v, "withholding_authority_ref") == nil {
			return invalid()
		}
		return s.authorized(termWithhold, stringAt(v, "withholding_authority_ref"), stringAt(v, "selected_by_ref"), at(v, "asset_ref"), at(v, "record_cut"))
	case termDisclosed, termDelivered:
		return s.exposure(v)
	default:
		return invalid()
	}
}

func (s *controlAgreement) selection(v any) error {
	snapshot := s.snapshot
	if stringAt(v, "scope_ref") != snapshot.ScopeRef || stringAt(v, termRunID) != snapshot.RunID || stringAt(v, fieldParticipantAddress) != snapshot.ParticipantAddress || stringAt(v, fieldEpisodeID) != snapshot.EpisodeID || stringAt(v, "audience_scope_ref") != snapshot.AudienceScopeRef || !numericEqual(at(v, "episode_generation"), snapshot.EpisodeGeneration) || !equal(at(v, "record_cut"), s.cut) {
		return invalid()
	}
	asset := s.resolve(at(v, "asset_ref"))
	if asset == nil {
		return invalid()
	}
	applicable := set(at(asset, "participant_addresses"))[snapshot.ParticipantAddress]
	for _, role := range snapshot.Roles[stringAt(v, "selection_cut", "cut_ref")] {
		applicable = applicable || set(at(asset, "role_refs"))[role]
	}
	if !applicable || s.lifecycle(at(v, "asset_ref"), at(v, "selection_cut")) != termActive {
		return invalid()
	}
	return s.authorized("select", stringAt(v, "selection_authority_ref"), stringAt(v, "selected_by_ref"), at(v, "asset_ref"), at(v, "selection_cut"))
}

func (s *controlAgreement) selectionHistory(v any) error {
	original := s.selections[stringAt(v, "selection_ref")]
	if original == nil {
		if stringAt(v, "disposition") != termSelected {
			return invalid()
		}
	} else {
		if stringAt(v, "disposition") != termSelected && (stringAt(original, "disposition") != termSelected || equal(at(original, "record_id"), at(v, "record_id"))) {
			return invalid()
		}
		if !matchingFields(v, original, "selection_ref", "scope_ref", termRunID, fieldParticipantAddress, fieldEpisodeID, "episode_generation", "audience_scope_ref", "asset_ref", "selected_by_ref", "selection_authority_ref", "selection_cut") {
			return invalid()
		}
	}
	return s.ordered(at(v, "selection_cut"), at(v, "record_cut"))
}

func (s *controlAgreement) exposure(v any) error {
	surface := s.surfaces[stringAt(v, termSurfaceID)]
	view, assurance := at(surface, "participant_view"), at(surface, "assurance")
	if surface == nil || !matchingFields(view, v, fieldParticipantAddress, fieldEpisodeID, termSurfaceID) || !equal(at(assurance, "audience_scope_ref"), at(v, "audience_scope_ref")) || !set(at(view, "visible_context_refs"))[stringAt(v, termItemRef)] {
		return invalid()
	}
	var binding any
	for _, candidate := range array(at(assurance, "exposure_bindings")) {
		if !equal(at(candidate, termItemRef), at(v, termItemRef)) {
			continue
		}
		if binding != nil {
			return invalid()
		}
		binding = candidate
	}
	if binding == nil || stringAt(binding, "source_ref") != "urn:"+stringAt(v, "asset_ref", "asset_digest") {
		return invalid()
	}
	if err := s.contextView(v, surface, binding); err != nil {
		return err
	}
	if err := s.exposureAuthority(v, surface, binding); err != nil {
		return err
	}
	if stringAt(v, "disposition") == termDelivered {
		return s.delivery(v, surface, binding)
	}
	return nil
}

func (s *controlAgreement) contextView(v, surface, binding any) error {
	view, assurance := at(surface, "participant_view"), at(surface, "assurance")
	context := s.views[stringAt(view, "context_view_ref")]
	if context == nil || !matchingFields(context, v, fieldParticipantAddress, fieldEpisodeID) || stringAt(context, "audience_scope") != "participant_visible" || !equal(at(context, "view_ref"), at(view, "context_view_ref")) || !equal(at(context, "payload_ref"), at(v, termItemRef)) || !equal(at(context, "visibility_projection_ref"), at(assurance, "visibility_projection_ref")) || !equal(at(context, "redaction_policy_ref"), at(view, "redaction_policy_ref")) || !subset(stringsOf(at(context, "marking_definition_refs")), set(at(view, "marking_definition_refs"))) {
		return invalid()
	}
	matches := 0
	for _, source := range array(at(context, "source_layers")) {
		if stringAt(source, "source_layer") == "participant_control_context_asset" && equal(at(source, "ref"), at(binding, "source_ref")) && equal(at(source, termSourceID), at(binding, "source_layer_ref")) && set(at(context, termTransformation, "input_source_ids"))[stringAt(source, termSourceID)] {
			matches++
		}
	}
	return require(matches == 1 && equal(at(context, termTransformation, "transformation_rule_ref"), at(binding, "transformation_rule_ref")))
}

func (s *controlAgreement) exposureAuthority(v, surface, binding any) error {
	cut := at(surface, "assurance", "derivation_anchor", "state_cut")
	if err := s.ordered(at(v, "selection_cut"), cut); err != nil {
		return err
	}
	if err := s.ordered(cut, at(v, "record_cut")); err != nil {
		return err
	}
	for _, point := range []any{cut, at(v, "record_cut")} {
		if s.lifecycle(at(v, "asset_ref"), point) != termActive {
			return invalid()
		}
		if err := s.authorized("disclose", stringAt(binding, "authority_basis_ref"), stringAt(binding, "actor_ref"), at(v, "asset_ref"), point); err != nil {
			return err
		}
	}
	return nil
}

func (s *controlAgreement) delivery(v, surface, binding any) error {
	delivery := at(surface, termDelivery)
	if stringAt(surface, "surface_state") != termDelivered || delivery == nil || !equal(at(delivery, termDeliveryRef), at(v, termDeliveryRef)) || !equal(at(delivery, "delivery_cut_ref"), at(v, "record_cut", "cut_ref")) {
		return invalid()
	}
	return s.authorized("deliver", stringAt(delivery, "delivery_authorization_ref"), stringAt(binding, "actor_ref"), at(v, "asset_ref"), at(v, "record_cut"))
}

func (s *controlAgreement) change(v any) error {
	if stringAt(v, "scope_ref") != s.snapshot.ScopeRef || !equal(at(v, "effective_cut"), s.cut) {
		return invalid()
	}
	asset := s.resolve(at(v, "asset_ref"))
	if asset == nil {
		return invalid()
	}
	expected := termActive
	if stringAt(v, "operation") == "publish" {
		expected = "unpublished"
		if !equal(at(v, "authority_ref"), at(asset, "publication_authority_ref")) {
			return invalid()
		}
	}
	if s.lifecycle(at(v, "asset_ref"), at(v, "effective_cut")) != expected {
		return invalid()
	}
	if successor := at(v, "successor_ref"); successor != nil {
		if s.resolve(successor) == nil || s.lifecycle(successor, at(v, "effective_cut")) != termActive {
			return invalid()
		}
	}
	return s.authorized(stringAt(v, "operation"), stringAt(v, "authority_ref"), stringAt(v, "actor_ref"), at(v, "asset_ref"), at(v, "effective_cut"))
}
