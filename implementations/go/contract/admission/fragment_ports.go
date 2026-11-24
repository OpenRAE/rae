package admission

import (
	"encoding/json"
	"maps"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// The Go ports of the fragment owner models that have no published
// definition. Each port names its reference model. A nested model with a
// published definition uses that definition.

const (
	termCleanupTemplate = "cleanup-template"
	termOpenWorld       = "open-world"
	termClosedWorld     = "closed-world"
	termSourceArtifact  = "source-artifact"
	termCompute         = "compute-substrate"
	termAction          = "action"
)

// Member names that the ports and the definition-level rules share.
const (
	fieldSourceProposalRef       = "source_proposal_ref"
	fieldControllerRef           = "controller_ref"
	fieldEffectiveOrder          = "effective_order"
	fieldAffectedOccurrenceRef   = "affected_occurrence_ref"
	fieldSupersededOccurrenceRef = "superseded_occurrence_ref"
	fieldSemantics               = "semantics"
	fieldProvenanceRefs          = "provenance_refs"
	fieldActionContractAddress   = "action_contract_address"
	fieldProposalRef             = "proposal_ref"
	fieldPolicyRevision          = "policy_revision"
	fieldAddress                 = "address"
	fieldReserved                = "reserved"
	fieldDomain                  = "domain"
	fieldDeclarationRef          = "declaration_ref"
	fieldProposalRevision        = "proposal_revision"
)

// nativeModel decodes the canonical fragment and applies a port.
func nativeModel(check func(e *Validator, v any) error) fragmentCheck {
	return func(e *Validator, data []byte, _ ingress.Limits) error {
		var document any
		if err := decodeExact(data, &document); err != nil {
			return fragmentInvalid()
		}
		return check(e, document)
	}
}

// shapeModel applies a closed shape and then the port rules.
func shapeModel(shape func(e *Validator) nativeShape, rules ...func(e *Validator, v any) error) fragmentCheck {
	return nativeModel(func(e *Validator, v any) error {
		if !shape(e).holds(v) {
			return invalid()
		}
		for _, rule := range rules {
			if err := rule(e, v); err != nil {
				return err
			}
		}
		return nil
	})
}

func portChecks() map[FragmentProfile]fragmentCheck {
	return map[FragmentProfile]fragmentCheck{
		TrialExecutionAuthority:         shapeModel(executionAuthorityShape),
		RealizationDesignation:          shapeModel(designationShape),
		RealizationConcern:              shapeModel(concernShape),
		RealizationValue:                nativeModel(func(*Validator, any) error { return nil }),
		RealizationConstraintEvaluation: shapeModel(relationResultShape),
		RealizationStructure:            nativeModel(func(e *Validator, v any) error { return require(e.legacyStructure()(v)) }),
		ValidatedActionSelection:        shapeModel(actionSelectionShape, func(_ *Validator, v any) error { return actionSelection(v) }),
		ParticipantResourceMeasurement:  shapeModel(measurementRequirementShape, func(_ *Validator, v any) error { return measurementRequirement(v) }),
		ParticipantControlPolicy:        controlPolicyFragment,
		ParticipantControlIntent:        nativeModel(func(_ *Validator, v any) error { return controlIntent(v) }),
		ParticipantControlDeclaration:   shapeModel(controlDeclarationNativeShape, func(_ *Validator, v any) error { return controlDeclarationShape(v) }),
		ParticipantInjectDelivery:       shapeModel(injectDeliveryShape),
		ParticipantCrossingEvidence:     shapeModel(crossingEvidenceShape),
		CompiledRealizationRequirement:  shapeModel(compiledRequirementShape, compiledRequirement),
		OpacitySupport:                  shapeModel(opacitySupportShape, func(_ *Validator, v any) error { return opacitySupport(v) }),
	}
}

func controlPolicyFragment(e *Validator, data []byte, _ ingress.Limits) error {
	_, err := e.controlPolicy(data)
	return err
}

// executionAuthorityShape ports TrialExecutionAuthorityModel.
func executionAuthorityShape(e *Validator) nativeShape {
	return nativeShape{required: map[string]nativeCheck{
		"attempt_timeout_seconds": integerFrom(1),
		"on_timeout":              oneOfTerms("cancel", "abort", "cleanup-and-fail"),
		"on_cancellation":         oneOfTerms("abort", "cleanup-and-fail"),
		"cleanup":                 e.cleanupTemplate,
	}}
}

// cleanupTemplate ports TrialCleanupTemplateModel. The reference model binds
// the template to fixed compiler identities and checks the bound plan.
func (e *Validator) cleanupTemplate(v any) bool {
	members := []string{"clean_state", "resource_boundaries", "cleanup_obligations", "retry_policy"}
	if !closedControlObject(v, members, nil) {
		return false
	}
	plan := map[string]any{"plan_id": termCleanupTemplate, "plan_entry_id": "entry-template", "run_id": "run-template"}
	for _, member := range members {
		plan[member] = object(v)[member]
	}
	data, err := json.Marshal(plan)
	return err == nil && e.CheckPortable(termTrialCleanupPlanV1, data, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) == nil
}

// designationShape ports the SDL designation resolution, RealizationResolution.
func designationShape(*Validator) nativeShape {
	return nativeShape{required: map[string]nativeCheck{
		"closure":         orNull(oneOfTerms(termOpenWorld, termClosedWorld)),
		"governing_scope": orNull(textOf(0)),
		"delegated":       isBoolean,
		termSource:        textOf(0),
	}}
}

// concernShape ports the declarative members of RealizationConcernDescriptor.
// The projection and validation callables are not part of a native document.
func concernShape(*Validator) nativeShape {
	return nativeShape{
		required: map[string]nativeCheck{
			"section":       textOf(0),
			"authored_path": listOf(0, textOf(0)),
			"concern_kind":  textOf(0),
			"payload_path":  listOf(0, textOf(0)),
		},
		optional: map[string]nativeCheck{
			"non_stateful_mounts_only":     isBoolean,
			"explicitness_excluded_fields": uniqueListOf(0, textOf(0)),
			"collection_identity_fields":   listOf(0, textOf(0)),
		},
	}
}

// relationResultShape ports RealizationRelationResult and its diagnostics.
func relationResultShape(*Validator) nativeShape {
	diagnostic := nativeShape{
		required: map[string]nativeCheck{"code": textOf(0), fieldDomain: textOf(0), fieldAddress: textOf(0), "message": textOf(0)},
		optional: map[string]nativeCheck{"severity": oneOfTerms("error", "warning", "info")},
	}
	return nativeShape{
		required: map[string]nativeCheck{"status": oneOfTerms("conformant", "nonconformant", "unresolved", "invalid", statusUnsupported, "limit-exceeded")},
		optional: map[string]nativeCheck{"diagnostics": listOf(0, diagnostic.holds)},
	}
}

// legacyStructure checks one member of the RealizationStructure union.
func (e *Validator) legacyStructure() nativeCheck {
	const plan = "provisioning-plan-v1"
	return taggedCheck(termKind, map[string]nativeCheck{
		postureExact: e.definitionCheck(plan, "ExactRealizationValue"),
		termOpen:     e.definitionCheck(plan, "OpenRealizationValue"),
		termRecord:   e.definitionCheck(plan, "RealizationRecord"),
		"collection": e.definitionCheck(plan, "RealizationCollection"),
	})
}

// actionSelectionShape ports ParticipantValidatedActionSelection.
func actionSelectionShape(*Validator) nativeShape {
	argument := listOf(0, func(v any) bool {
		pair, ok := v.([]any)
		return ok && len(pair) == 2 && textOf(1)(pair[0]) && flowArgumentValue(pair[1])
	})
	shape := nativeShape{
		required: map[string]nativeCheck{
			fieldActionContractAddress: textOf(1),
			"argument_shape_ref":       textOf(1),
			fieldProposalRef:           textOf(1),
			"normalized_arguments":     argument,
		},
		optional: map[string]nativeCheck{},
	}
	for _, field := range []string{"defaulted_argument_names", "omitted_argument_names", "normalization_disclosure_refs", "omission_disclosure_refs", "default_disclosure_refs", "loss_disclosure_refs"} {
		shape.optional[field] = uniqueListOf(0, textOf(1))
	}
	return shape
}

// actionSelection requires a compiled action contract and canonical,
// unique argument names.
func actionSelection(v any) error {
	if !strings.HasPrefix(stringAt(v, fieldActionContractAddress), "participant.action-contract.") {
		return invalid()
	}
	names := make([]string, 0, len(array(at(v, "normalized_arguments"))))
	for _, pair := range array(at(v, "normalized_arguments")) {
		names = append(names, text(array(pair)[0]))
	}
	return require(unique(names) && slices.IsSorted(names))
}

// measurementRequirementShape ports ParticipantResourceMeasurementRequirementModel.
func measurementRequirementShape(e *Validator) nativeShape {
	return nativeShape{required: map[string]nativeCheck{
		"budget_state_ref":  textOf(1),
		"resource_kind":     anyOfChecks(oneOfTerms(termActionRate, termConcurrentActions, termStorageGrowth, termInferenceTokens, termImageGenerations, termAccelerator), e.definitionCheck(termBackendManifestV2, "DomainProfileCoordinateModel")),
		"unit":              textOf(1),
		"meter_profile_ref": textOf(1),
		fieldReserved:       integerWithin(big.NewRat(0, 1), new(big.Rat).SetInt(new(big.Int).Exp(big.NewInt(10), big.NewInt(18), nil))),
	}}
}

// measurementRequirement requires the unit of a portable resource kind. Each
// portable kind has supported quantity semantics.
func measurementRequirement(v any) error {
	if object(at(v, "resource_kind")) != nil {
		return nil
	}
	return require(stringAt(v, "unit") == resourceUnit(stringAt(v, "resource_kind")))
}

// controlDeclarationNativeShape ports the member types of
// ParticipantControlDeclarationModel; controlDeclarationShape keeps its rules.
func controlDeclarationNativeShape(*Validator) nativeShape {
	shape := nativeShape{required: map[string]nativeCheck{
		termKind:                  oneOfTerms(termProposal, termApproval, termDenial, termExternalDirection, termIntervention, termHandoff, termOverride, termCancellation),
		termAuthorityBasisRefs:    listOf(1, textOf(1)),
		"controlled_scope_refs":   listOf(1, textOf(1)),
		termExpectedStateRevision: integerFrom(0),
		fieldEffectiveOrder:       integerFrom(0),
		termValidFromOrder:        integerFrom(0),
		termValidUntilOrder:       integerFrom(0),
	}}
	for _, field := range []string{fieldDeclarationRef, fieldParticipantAddress, fieldEpisodeID, fieldControllerRef, "controller_state_ref", "behavior_specification_ref", "mixed_control_policy_ref", fieldPolicyRevision} {
		shape.required[field] = textOf(1)
	}
	return shape
}

// injectDeliveryShape ports the compiled ParticipantInjectDeliveryRuntime.
func injectDeliveryShape(*Validator) nativeShape {
	shape := nativeShape{
		required: map[string]nativeCheck{fieldAddress: textOf(0), termName: textOf(0), "spec": isObject},
		optional: map[string]nativeCheck{"control": orNull(injectDeliveryControlShape().holds)},
	}
	for _, field := range []string{termBindingID, "behavior_specification_address", fieldParticipantAddress, "inject_address", "event_address", "script_address", "story_address", "source_item_ref", "source_item_address", "result_item_ref", "result_item_address", "observation_boundary_address", "delivery_kind", "policy_ref", fieldPolicyRevision, "exposure_policy_ref", "audience_scope_ref", "visibility_basis_ref", "disclosure_basis_ref", "order_basis", "failure_disposition", "control_transition_address", "controller_address"} {
		shape.optional[field] = textOf(0)
	}
	for _, field := range []string{"ordering_dependencies", "refresh_dependencies", "temporal_constraint_addresses", "evidence_requirement_addresses", "control_authority_scope_refs", "control_authority_scope_addresses", "control_evidence_refs", "control_evidence_addresses"} {
		shape.optional[field] = listOf(0, textOf(0))
	}
	for _, field := range []string{"control_effective_order", "control_valid_from_order", "control_valid_until_order"} {
		shape.optional[field] = orNull(integerWithin(nil, nil))
	}
	return shape
}

// injectDeliveryControlShape ports ParticipantInjectDeliveryControlRuntime.
func injectDeliveryControlShape() nativeShape {
	shape := nativeShape{optional: map[string]nativeCheck{}}
	for _, field := range []string{fieldSemantics, fieldPolicyRevision, "permitted_transition_address", "controller_address"} {
		shape.optional[field] = textOf(0)
	}
	for _, field := range []string{fieldAuthorityScopeRefs, "authority_scope_addresses", fieldEvidenceRefs, "evidence_addresses"} {
		shape.optional[field] = listOf(0, textOf(0))
	}
	return shape
}

// crossingEvidenceShape ports ParticipantCrossingEvidence.
func crossingEvidenceShape(*Validator) nativeShape {
	shape := nativeShape{required: map[string]nativeCheck{"audience_scope_ref": textOf(1), "authorization_scope": textOf(1)}}
	for _, field := range []string{"required_evidence_refs", fieldProvenanceRefs, fieldEvidenceRefs, "object_marking_refs", "loss_and_limitations"} {
		shape.required[field] = listOf(1, textOf(1))
	}
	return shape
}

// opacitySupportShape ports ParticipantOpacityRuntimeSupportModel.
func opacitySupportShape(e *Validator) nativeShape {
	return nativeShape{required: map[string]nativeCheck{
		"binding":                       e.definitionCheck("participant-crossing-occurrence-v1", "ParticipantOpacityRuntimeEnforcementBindingModel"),
		"observation_inventory":         opacityInventory,
		"predicate_positive_case_ref":   textOf(1),
		"predicate_negative_case_ref":   textOf(1),
		"initial_information_digest":    prefixedDigest,
		"normalized_observation_digest": prefixedDigest,
	}}
}

// opacityInventory ports ParticipantOpacityObservationInventoryModel.
func opacityInventory(v any) bool {
	shape := nativeShape{required: map[string]nativeCheck{
		"inventory_ref":      textOf(1),
		"inventory_revision": textOf(1),
		"observer_ref":       textOf(1),
		"audience_ref":       textOf(1),
		"surfaces":           listOf(1, opacitySurface),
	}}
	surfaces := array(at(v, "surfaces"))
	return shape.holds(v) && len(surfaces) <= 64 && len(rowSet(surfaces, "surface_ref")) == len(surfaces)
}

// opacitySurface ports ParticipantOpacityObservationSurfaceModel.
func opacitySurface(v any) bool {
	shape := nativeShape{
		required: map[string]nativeCheck{
			"profile_channel":      oneOfTerms("participant-state", "payload", "decision", "action-availability", "delivery", "retry", "latency", "order", "policy-release"),
			"disposition":          oneOfTerms("mediated", "unreachable", statusUnsupported),
			"occurrence_treatment": oneOfTerms("observable", "hidden", "not-applicable"),
			"content_treatment":    oneOfTerms("projected", "hidden", "not-applicable"),
		},
		optional: map[string]nativeCheck{},
	}
	for _, field := range []string{"surface_ref", "owner_ref", "projection_ref", "projection_revision", "order_basis_ref", "order_basis_revision"} {
		shape.required[field] = textOf(1)
	}
	for _, field := range []string{"opportunity_basis_ref", "opportunity_basis_revision", "timing_bucket_ref", "timing_bucket_revision", "limitation_ref"} {
		shape.optional[field] = orNull(textOf(1))
	}
	present := func(field string) bool { return at(v, field) != nil }
	if !shape.holds(v) || present("opportunity_basis_ref") != present("opportunity_basis_revision") || present("timing_bucket_ref") != present("timing_bucket_revision") {
		return false
	}
	return stringAt(v, "disposition") != statusUnsupported || present("limitation_ref")
}

// opacitySupport joins the inventory to its durable binding and requires
// distinct secret and nonsecret cases. The inventory digest covers the
// inventory with its defaults.
func opacitySupport(v any) error {
	inventory, binding := at(v, "observation_inventory"), at(v, "binding")
	defaulted := maps.Clone(object(inventory))
	surfaces := make([]any, 0, len(array(at(inventory, "surfaces"))))
	for _, surface := range array(at(inventory, "surfaces")) {
		row := map[string]any{"opportunity_basis_ref": nil, "opportunity_basis_revision": nil, "timing_bucket_ref": nil, "timing_bucket_revision": nil, "limitation_ref": nil}
		maps.Copy(row, object(surface))
		surfaces = append(surfaces, row)
	}
	defaulted["surfaces"] = surfaces
	digest, err := jsonDigest(defaulted)
	if err != nil || !equal(at(inventory, "inventory_ref"), at(binding, "observation_inventory_ref")) || !equal(at(inventory, "inventory_revision"), at(binding, "observation_inventory_revision")) || digest != stringAt(binding, "observation_inventory_digest") {
		return invalid()
	}
	return require(!equal(at(v, "predicate_positive_case_ref"), at(v, "predicate_negative_case_ref")))
}

// compiledRequirementShape ports CompiledRealizationRequirement.
func compiledRequirementShape(e *Validator) nativeShape {
	const plan = "provisioning-plan-v1"
	domains := map[string]nativeCheck{}
	for kind, name := range map[string]string{postureExact: "ExactDomain", termEnum: "EnumDomain", typeBoolean: "BooleanDomain", termNumericInterval: "NumericIntervalDomain", termGovernedReference: "GovernedReferenceDomain", termRecord: "RecordDomain"} {
		domains[kind] = e.definitionCheck(plan, name)
	}
	valueConstraint := nativeShape{required: map[string]nativeCheck{"identity_digest": textOf(0), "leaf": textOf(0), "parameter": listOf(0, textOf(0)), "allowed_values": listOf(0, func(any) bool { return true })}}
	limitDemand := nativeShape{required: map[string]nativeCheck{
		"identity_digest": textOf(0),
		"resource":        oneOfTerms("open_file_descriptors", "locked_memory_bytes"),
		"scope":           oneOfTerms("process", "subtree"),
		"soft":            anyOfChecks(integerWithin(nil, nil), textOf(0)),
		"hard":            anyOfChecks(integerWithin(nil, nil), textOf(0)),
	}}
	return nativeShape{
		required: map[string]nativeCheck{
			"field_path":       textOf(0),
			fieldAddress:       textOf(0),
			fieldDomain:        textOf(0),
			"requirement_kind": textOf(0),
			"explicitness":     orNull(oneOfTerms(postureExact, termConstrained, termOpen)),
			"provenance":       oneOfTerms("author-declared", "processor-derived", "backend-realized"),
		},
		optional: map[string]nativeCheck{
			"governing_scope":               orNull(textOf(0)),
			"delegated":                     isBoolean,
			"artifact_requirement":          orNull(e.definitionCheck("instantiated-scenario-v1", "ArtifactRequirement")),
			"verification_scope":            orNull(oneOfTerms("presence", "configuration")),
			"required_observation_strength": orNull(oneOfTerms(postureNone, "driver-reported", "daemon-observed", "guest-observed")),
			"value_domain":                  orNull(taggedCheck(termKind, domains)),
			"constraint_provenance":         orNull(textOf(0)),
			"value_constraints":             listOf(0, valueConstraint.holds),
			"process_resource_limits":       listOf(0, limitDemand.holds),
			"structure":                     orNull(e.legacyStructure()),
			"constraint_document":           orNull(e.definitionCheck("plan-realization-profiles-v1", "RealizationConstraintDocument")),
			"constraint_binding":            orNull(textOf(0)),
			"structure_error":               isBoolean,
			"recursive_pending":             isBoolean,
		},
	}
}

// compiledRequirement applies the rules of CompiledRealizationRequirement.
func compiledRequirement(e *Validator, v any) error {
	structure, document := at(v, "structure") != nil, at(v, "constraint_document") != nil
	if !address.Valid(stringAt(v, fieldAddress)) || structure && document || document != (at(v, "constraint_binding") != nil) {
		return invalid()
	}
	if boolean(at(v, "recursive_pending")) && (structure || document) || boolean(at(v, "delegated")) != (at(v, "explicitness") == nil) {
		return invalid()
	}
	kind := stringAt(v, "requirement_kind")
	if err := processLimitMetadata(kind, v); err != nil {
		return err
	}
	if err := e.requirementDomain(kind, v); err != nil {
		return err
	}
	if artifact := at(v, "artifact_requirement"); artifact != nil {
		return require(kind == termSourceArtifact && equal(at(v, "explicitness"), at(artifact, "explicitness")))
	}
	return nil
}

// processLimitMetadata checks the finite value domains and limit demands,
// which only a process-resource-limits requirement carries.
func processLimitMetadata(kind string, v any) error {
	constraints := array(at(v, "value_constraints"))
	if kind != "process-resource-limits" && (len(constraints) > 0 || len(array(at(v, "process_resource_limits"))) > 0) {
		return invalid()
	}
	for _, constraint := range constraints {
		leaf := stringAt(constraint, "leaf")
		if !strings.HasPrefix(stringAt(constraint, "identity_digest"), digest.Prefix) || leaf != "soft" && leaf != "hard" || len(array(at(constraint, "parameter"))) == 0 || len(array(at(constraint, "allowed_values"))) == 0 {
			return invalid()
		}
	}
	return nil
}

// requirementDomain checks the constraint domain metadata of a compiled
// realization requirement.
func (e *Validator) requirementDomain(kind string, v any) error {
	domain, explicitness := at(v, "value_domain"), at(v, "explicitness")
	switch kind {
	case termCompute:
		return e.substrateDomain(text(explicitness), domain)
	case "os-family", "os-distribution", "os-version":
		if domain != nil && (stringAt(domain, termKind) != termEnum || text(explicitness) != termConstrained) {
			return invalid()
		}
		return require(at(v, "constraint_provenance") == nil || domain != nil)
	}
	return require(domain == nil && at(v, "constraint_provenance") == nil)
}

// controlIntent ports the runtime ParticipantControlIntent union.
func controlIntent(v any) error {
	shapes := controlIntentShapes()
	kind, _ := object(v)[termKind].(string)
	shape, known := shapes[kind]
	if !known || !shape.holds(v) {
		return invalid()
	}
	if at(v, "application") != nil {
		for name, member := range object(v) {
			if strings.HasSuffix(name, "revision") && name != fieldPolicyRevision && member != nil && !controlCount(member) {
				return invalid()
			}
		}
	}
	if kind == termProposal {
		return require((at(v, "payload_ref") == nil) != (at(v, "payload_digest") == nil))
	}
	return nil
}

// controlIntentShapes returns the closed shape of each intent kind.
func controlIntentShapes() map[string]nativeShape {
	positive := integerFrom(1)
	specific := map[string]map[string]nativeCheck{
		termProposal:          {"proposal_id": textOf(1), fieldProposalRevision: positive, "action_contract_ref": textOf(1)},
		termApproval:          {fieldProposalRef: textOf(1), fieldProposalRevision: positive, "decision_ref": textOf(1), "decision_revision": positive},
		termDenial:            {fieldProposalRef: textOf(1), fieldProposalRevision: positive, "decision_ref": textOf(1), "decision_revision": positive},
		termExternalDirection: {termTargetKind: oneOfTerms(termProposal, termAction, "control"), termTargetRef: textOf(1), "target_revision": positive},
		termIntervention:      {"affected_target_kind": oneOfTerms(termAction, "control", "attempt"), fieldAffectedOccurrenceRef: textOf(1), "affected_revision": positive, "intervention_ref": textOf(1)},
		termHandoff:           {"completion_evidence_ref": textOf(1)},
		termOverride:          {"superseded_target_kind": oneOfTerms("control", "decision"), fieldSupersededOccurrenceRef: textOf(1), "superseded_revision": positive, "replacement_ref": textOf(1)},
		termCancellation:      {termTargetKind: oneOfTerms(termProposal, "decision", "admitted-action", "attempt"), termTargetRef: textOf(1), "target_revision": positive},
	}
	shapes := map[string]nativeShape{}
	for kind, members := range specific {
		shape := controlIntentBase(kind)
		maps.Copy(shape.required, members)
		if kind == termProposal {
			for _, field := range []string{"decision_surface_ref", "proposal_binding_ref", "payload_ref", "payload_digest", fieldSourceProposalRef, "transformation_ref"} {
				shape.optional[field] = orNull(textOf(0))
			}
			shape.optional["source_proposal_revision"] = orNull(positive)
		}
		shapes[kind] = shape
	}
	return shapes
}

// controlIntentBase ports ParticipantControlIntentBase with the intent kind.
func controlIntentBase(kind string) nativeShape {
	application := nativeShape{
		required: map[string]nativeCheck{
			fieldSemantics:          oneOfTerms("mixed-control-policy-occurrence/rev1"),
			"policy_ref":            controlReference,
			"prior_state_ref":       controlReference,
			"expected_history_head": controlCount,
			fieldEffectiveOrder:     controlCount,
		},
		optional: map[string]nativeCheck{"script_step_ref": orNull(controlReference)},
	}
	shape := nativeShape{
		required: map[string]nativeCheck{termKind: oneOfTerms(kind), termExpectedStateRevision: integerFrom(0)},
		optional: map[string]nativeCheck{"application": orNull(application.holds)},
	}
	for _, field := range []string{fieldDeclarationRef, fieldEpisodeID, "client_correlation_id", fieldPolicyRevision} {
		shape.required[field] = textOf(1)
	}
	for _, field := range []string{fieldProvenanceRefs, fieldEvidenceRefs, "object_marking_refs", "limitation_refs"} {
		shape.required[field] = listOf(1, textOf(0))
	}
	return shape
}
