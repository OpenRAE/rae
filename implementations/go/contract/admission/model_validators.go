package admission

import (
	"maps"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
)

// Definition-level model rules. Each rule ports the validator of the reference
// model with the definition's name. The rule applies wherever the definition
// occurs: in a published document and in a native fragment. The rules read
// absent members as their published defaults.

const (
	termAutonomousExecutionV1 = "participant-autonomous-execution/v1"
	termCaptureSpec           = "capture-spec"
	maxCollectionItems        = 4096
	termOther                 = "other"
)

// definitionModel applies the rule of a model definition, if it has one.
func (e *Validator) definitionModel(instance validation.SchemaInstance) error {
	name := strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix)
	if name == "ParticipantTemporalBindingModel" {
		return e.defaultedTemporalBinding(instance)
	}
	if name == "ControlMechanismBindingModel" || name == "ControlMechanismBindingV2Model" {
		return e.controlBinding(instance.Value)
	}
	if rule, known := e.definitions[name]; known {
		return rule(instance.Value)
	}
	return nil
}

func definitionRules() map[string]func(any) error {
	rules := map[string]func(any) error{
		"NodePresenceAlternative":                 sdlNodePresence,
		"ServiceMaterialization":                  sdlServiceMaterializationFields,
		"ServiceSearchIndexSchemaMaterialization": sdlServiceMaterializationFields,
		"ExperimentArtifactRefModel":              func(v any) error { return timestamps(v, "created_at") },
		"RealizationDesignation":                  sdlDesignation,
		"OrderVariationPoint":                     sdlOrder,
		"AlternativeVariationPoint":               sdlAlternative,
		"ParticipantInjectDelivery":               sdlInjectDelivery,
		"ParticipantControlContextAssetModel": func(v any) error {
			return controlContextLocal(termParticipantControlContextAssetV1, v)
		},
		"AugmentationScopePolicy":                augmentationScopeModel,
		"IdentityDomain":                         sdlIdentityDomain,
		"ArtifactConstraint":                     sdlUniqueLists("allowed_values"),
		"ArtifactMechanismProfile":               sdlArtifactProfile,
		"ParticipantBehaviorSpecification":       behaviorSpecificationModel,
		"ImageConfig":                            imageConfigShape,
		"ContainerImageBuildProvenance":          imageBuildShape,
		"ImageBuildArg":                          imageEnvironmentName,
		"ImageEnvironmentDefault":                imageEnvironmentName,
		"ImageSourceInput":                       imageSourceInput,
		"ImageCopiedSource":                      imageCopiedSource,
		"ParticipantControlContextReference":     func(v any) error { work := 0; return require(materializationConcrete(at(v, "asset_ref"), &work)) },
		"TimeDomain":                             sdlTimeDomain,
		"TimeDomainMapping":                      sdlTimeMapping,
		"TimeProgressionPolicy":                  sdlTimeProgression,
		"TemporalConstraint":                     sdlTemporalConstraint,
		"ParticipantActionContract":              sdlActionContract,
		"ParticipantActionArgumentDefinition":    sdlActionArgument,
		"ParticipantInteractionDeclaration":      sdlInteraction,
		"ParticipantViewRule":                    sdlViewRule,
		"ParticipantViewTransition":              sdlViewTransition,
		"ParticipantObservationBoundary":         sdlObservationBoundary,
		"ParticipantEvaluationAuthority":         sdlEvaluationAuthority,
		"ParticipantActivityTiming":              func(v any) error { return sdlOptionalInterval(v, "minimum_ticks", "maximum_ticks") },
		"ParticipantActivityActionCandidate":     sdlActivityCandidate,
		"ParticipantAutonomousExecutionPolicyV1": func(v any) error { return require(nonblankSDLRefs(v, "temporal_constraint_refs", "action_order")) },
		"ParticipantAutonomousExecutionPolicyV2": sdlActivityPolicy,
		"ParticipantAutonomousExecutionPolicyV3": sdlResourceActivityPolicy,
		"ParticipantResourceBudgetDimension":     sdlResourceDimension,
		"ParticipantResourceBudgetPolicy":        sdlResourcePolicy,
		"ParticipantSharedTimeBinding":           sdlSharedTimeBinding,
		"ParticipantTemporalContract":            sdlParticipantTemporal,
		"ParticipantBackendTimingDisclosure":     sdlTimingDisclosure,
		"MixedControlControllerState":            sdlControllerState,
		"MixedControlTransition":                 sdlMixedTransition,
		"MixedControlParticipantOperation":       sdlMixedOperation,
		"MixedControlPolicy":                     sdlMixedPolicy,
		"MixedControlPermittedTransition": func(v any) error {
			return sdlOptionalInterval(v, termValidFromOrder, termValidUntilOrder)
		},
		"MixedControlScriptStep":                sdlMixedScriptStep,
		"RandomValueFormat":                     sdlRandomFormat,
		"RandomValueRecipe":                     func(v any) error { return randomRecipe(v, countAt(v, "min_entropy_bits")) },
		"ParticipantActionPrecondition":         sdlActionPrecondition,
		"ParticipantActionEffect":               sdlActionEffect,
		"ParticipantBackendFailureMapping":      func(v any) error { return require(nonblankSDLFields(v, "backend_error_code", "diagnostic")) },
		"Node":                                  sdlNode,
		"ServicePort":                           sdlServicePort,
		"InfraNode":                             sdlInfrastructure,
		"RuntimeApplicationRoute":               sdlApplicationRoute,
		"RuntimeApplicationSurface":             sdlApplicationSurface,
		"RuntimeCapabilityPolicy":               sdlCapabilityPolicy,
		"RuntimeProcessCapabilityOverride":      sdlCapabilityOverride,
		"RuntimeContainerConfiguration":         sdlContainerConfiguration,
		"RuntimeLocalIdentityInventory":         sdlIdentityInventory,
		"RuntimeLocalUser":                      sdlLocalUser,
		"RuntimeLocalGroup":                     func(v any) error { return require(nonblankSDLFields(v, termName)) },
		"RuntimeSudoRule":                       func(v any) error { return require(nonblankSDLFields(v, "principal")) },
		"RuntimeProcessIdentity":                func(v any) error { return require(sdlAbsoluteFields(v, true, termWorkingDirectory)) },
		"RuntimeDeviceMapping":                  func(v any) error { return require(sdlAbsoluteFields(v, false, "host_path", "container_path")) },
		"RuntimeExtraHost":                      func(v any) error { return require(nonblankSDLFields(v, "hostname", "address")) },
		"RuntimeNetworkNamespace":               func(v any) error { return require(nonblankSDLFields(v, "target_node_ref")) },
		"RuntimeInitProcess":                    func(v any) error { return require(sdlAbsoluteFields(v, true, "executable_path")) },
		"RuntimeSoftwareComponentHash":          func(v any) error { return require(nonblankSDLFields(v, "algorithm", "value")) },
		"RuntimeAptPackageRepository":           sdlAptRepository,
		"RuntimePackageRepositorySigningKey":    func(v any) error { return require(sdlHTTPS(stringAt(v, "uri"))) },
		"RuntimePackage":                        sdlPackage,
		"RuntimePublishedPort":                  sdlPublishedPort,
		"RuntimeNetworkEndpoint":                sdlNetworkEndpoint,
		"RuntimeNetworkRealization":             sdlNetworkRealization,
		"RuntimeNetworkSensor":                  sdlNetworkSensor,
		"RuntimeNetworkDetectionEngine":         sdlNetworkDetectionEngine,
		"RuntimeNetworkDetectionNetworkSet":     sdlNetworkSet,
		"RuntimeNetworkDetectionOutputStream":   func(v any) error { return require(sdlSymbolField(v, "stream_id") && fieldsUnique(v, "event_types")) },
		"RuntimeNetworkDetectionControlChannel": func(v any) error { return require(sdlSymbolField(v, "channel_id") && fieldsUnique(v, "capabilities")) },
		"SshMatchRule":                          sdlSSHMatch,
		"SshMatchCriterion":                     func(v any) error { return require(nonblankSDLFields(v, "pattern")) },
		"RuntimeSshServer":                      sdlSSHServer,
		"SshForcedCommand":                      func(v any) error { return sdlCommand(v, true) },
		"ServiceUnitExecStart":                  func(v any) error { return sdlCommand(v, false) },
		"ServiceManagerUnit":                    sdlServiceManagerUnit,
		"RuntimeProcessResourceLimit":           sdlProcessLimit,
		"RuntimeResourceLimits":                 sdlResourceLimits,
		"RuntimeEnvironmentVariable":            sdlEnvironmentVariable,
		"RuntimeMount":                          func(v any) error { return require(sdlAbsoluteFields(v, false, "target")) },
		"RuntimeControlInterface":               sdlControlInterface,
		"RuntimeAppAuthorization":               sdlLocalIdentities("app_authorization_id", [2]string{"principals", "principal_id"}, [2]string{termRoles, "role_id"}, [2]string{"permission_grants", "grant_id"}, [2]string{"role_mappings", termMappingID}, [2]string{"tenants", "tenant_id"}),
		"RuntimeAppAuthorizationGrant":          sdlUniqueLists("actions", "resource_patterns"),
		"RuntimeAppAuthorizationPrincipal":      sdlUniqueLists("backend_roles"),
		"RuntimeAppAuthorizationRoleMapping":    sdlUniqueLists("backend_roles", "users", "hosts"),
		"Database":                              sdlUniqueCollections([2]string{"schemas", "schema_id"}),
		"DatabaseSchema":                        sdlUniqueCollections([2]string{"tables", "table_id"}),
		"DatabaseGrant":                         sdlDatabaseGrant,
		"RuntimeDatabaseService":                sdlDatabaseService,
		"RuntimeIdentityAuthority":              sdlLocalIdentities("identity_authority_id", [2]string{"services", "service_id"}, [2]string{"subjects", "subject_id"}, [2]string{"policies", "policy_id"}, [2]string{"relationships", "relationship_id"}, [2]string{"resource_scopes", "scope_id"}, [2]string{"identity_uses", "use_id"}, [2]string{"access_observations", termObservationID}),
		"RuntimeIdentityRelationship": func(v any) error {
			return require((stringAt(v, "target_ref") != "") != (stringAt(v, "external_target") != ""))
		},
		"RuntimeIdentityPolicy": func(v any) error {
			return require(fieldsUnique(v, "applies_to_refs") && sdlUniqueKey(at(v, termSettings), termName, false))
		},
		"RuntimeIdentitySubject": func(v any) error {
			return require(fieldsUnique(v, "service_principal_names") && sdlUniqueKey(at(v, "attributes"), termName, false))
		},
		"DnsSoaRdata":  func(v any) error { return require(sdlDNSNames(v, "mname", "rname")) },
		"DnsMxRdata":   func(v any) error { return require(sdlDNSNames(v, "exchange")) },
		"DnsSrvRdata":  func(v any) error { return require(sdlDNSNames(v, "target")) },
		"DnsForwarder": func(v any) error { return require(sdlDNSNames(v, fieldAddress)) },
		"DnsResolverPolicy": func(v any) error {
			for _, item := range stringsOf(at(v, "allow_recursion")) {
				if !sdlDNSName(item) {
					return invalid()
				}
			}
			return nil
		},
		"DnsZone":                                 sdlDNSZone,
		"DnsResourceRecordSet":                    sdlDNSRRSet,
		"DnsResourceRecord":                       sdlDNSRecord,
		"RuntimeDnsService":                       sdlDNSService,
		"RuntimeDatastoreService":                 sdlDatastoreService,
		"RuntimeDatastoreNode":                    sdlDatastoreNode,
		"RuntimeDatastoreMapping":                 sdlUniqueLists("evidence_refs"),
		"RuntimeDatastoreTemplate":                sdlUniqueLists("index_patterns", "evidence_refs"),
		"RuntimeFileService":                      sdlLocalIdentities("file_service_id", [2]string{"shares", "share_id"}, [2]string{"principals", "principal_id"}, [2]string{"access_rules", "rule_id"}, [2]string{"access_observations", termObservationID}),
		"RuntimeMailService":                      sdlLocalIdentities("mail_service_id", [2]string{"components", termComponentID}, [2]string{"listeners", "listener_id"}, [2]string{termDomains, "domain_id"}, [2]string{"mailbox_stores", "store_id"}, [2]string{"mailboxes", "mailbox_id"}, [2]string{"aliases", "alias_id"}, [2]string{"routing_rules", "rule_id"}, [2]string{"queues", "queue_id"}, [2]string{termSettings, termSettingID}),
		"RuntimeForwardingAgent":                  sdlLocalIdentityRule("forwarding_agent_id", materializationQualified, [2]string{"sources", termSourceID}, [2]string{"transforms", "transform_id"}, [2]string{"ship_targets", "target_id"}, [2]string{"reload_channels", "reload_channel_id"}, [2]string{termSettings, termSettingID}),
		"RuntimeOrchestrationAuthority":           sdlLocalIdentities("orchestration_authority_id", [2]string{"spawn_templates", "template_id"}, [2]string{"realized_children", "workload_id"}),
		"RuntimePlatformApplication":              sdlLocalIdentities("platform_application_id", [2]string{"capabilities", "capability_id"}, [2]string{"organizations", "organization_id"}, [2]string{"tenants", "tenant_id"}, [2]string{"content_objects", "content_object_id"}, [2]string{"markings", "marking_id"}, [2]string{"upstream_bindings", termBindingID}, [2]string{"connectors", "connector_id"}, [2]string{termSettings, termSettingID}, [2]string{"secrets", "secret_id"}, [2]string{"cloud_limits", "limit_id"}),
		"RuntimeSecurityMonitoringManager":        sdlLocalIdentities("security_monitoring_manager_id", [2]string{"listeners", "listener_id"}, [2]string{"components", termComponentID}, [2]string{"agents", "agent_id"}, [2]string{"agent_groups", "group_id"}, [2]string{"content_sets", "content_id"}, [2]string{"detection_definitions", "definition_id"}, [2]string{termSettings, termSettingID}),
		"RuntimePlatformApplicationCapability":    sdlUniqueLists("evidence_refs"),
		"RuntimePlatformApplicationContentObject": sdlUniqueLists("references", "marking_refs", "evidence_refs"),
		"RuntimeSecretConsumer":                   sdlSecretConsumer,
		"RuntimeSecretVersion": func(v any) error {
			return require(stringAt(v, "state") != "destroyed" || stringAt(v, "payload_content_ref") == "")
		},
		"RuntimeServiceSecret":                         sdlServiceSecret,
		"RuntimeIdentityAccessObservation":             sdlAccessObservation,
		"RuntimeIdentityPermissionBinding":             sdlPermissionBinding,
		"RuntimeIdentityResourceAccess":                sdlIdentityResourceAccess,
		"RuntimeSecurityMonitoringDetectionDefinition": sdlSecurityDefinition,
		"RuntimeIdentityAttribute":                     sdlIdentityAttribute,
		"RuntimeServiceListener":                       sdlListenerModel,
		"RuntimePublishedPortRef":                      sdlPublishedPort,
		"RelationshipForwardingEdge":                   sdlForwardingEdge,
		"Objective":                                    sdlObjective,
		"WorkflowCompensationPolicy":                   sdlCompensationPolicy,
		"WorkflowPredicate":                            sdlWorkflowPredicate,
		"WorkflowStepStateRef":                         sdlUniqueLists("outcomes"),
		"SelectionRelation":                            sdlUniqueLists("members"),
		"OrderPrecedence":                              func(v any) error { return require(stringAt(v, "before") != stringAt(v, "after")) },
		"ArtifactMaterializationSpecification":         sdlMaterializationSpecification,
		"GeneratedArtifact":                            generatedArtifact,
		"GeneratedArtifactConsumer":                    sdlUniqueLists("selected_outputs"),
		"PersistentVolume":                             persistentVolume,
		"RuntimeConfiguration":                         sdlRuntimeConfiguration,
		"RuntimeSoftwareComponent":                     sdlSoftwareComponent,
		"RuntimeSoftwareRepositoryState":               sdlRepositoryState,
		"RuntimeSoftwareRepository":                    func(v any) error { return sdlRepositoryRefinements(v, "repository-state") },
		"RuntimeSoftwareTrustBinding":                  func(v any) error { return sdlRepositoryRefinements(v, "repository-trust") },
		"Proposition":                                  propositionShape,
		"StringPredicate":                              stringPredicateShape,
		"ExactRatio": func(v any) error {
			return require(reducedRatio(v))
		},
		"Condition":            probeShape,
		"Content":              contentAnchors,
		"Account":              func(v any) error { return require(stringAt(v, "node") != "") },
		"ObjectiveSuccess":     successCriteria,
		"SubsetVariationPoint": subsetBounds,
		"WorkflowStep":         workflowShape,
		"Clock":                clockJump,
		"ImageAttestation": func(v any) error {
			return require(stringAt(v, "status") != "absent" || stringAt(v, "verification") != "verified")
		},
		"RuntimeFilesystemEntry":                           runtimeFilesystemModel,
		"AdmittedApparatusBindingModel":                    apparatusBindingModel,
		"AdmittedMixedCompositionBindingModel":             mixedCompositionBindingModel,
		"AdmittedTrialPlanInputRefsModel":                  trialInputRefsModel,
		"ArtifactMechanismCapability":                      func(v any) error { return require(uniqueRows(at(v, "supported_routes"), "acquisition", "timing")) },
		"CleanupObligationResultModel":                     cleanupResult,
		"ControlProfileObligationV2Model":                  controlProfileObligation,
		"ControlResultSlotV2Model":                         controlResultSlot,
		"EvidenceRequirement":                              evidenceRequirementModel,
		"ExecutionRetryPolicyModel":                        retryPolicy,
		"GovernedReferenceDomain":                          domainDescriptorModel(termGovernedReference),
		"NumericIntervalDomain":                            domainDescriptorModel(termNumericInterval),
		"InjectTriggerRequestModel":                        func(v any) error { return injectRequest(validation.Invocation{Instance: v}) },
		"InjectEventPlacementModel":                        injectPlacement,
		"InjectSchedulePlacementModel":                     injectPlacement,
		"ParticipantAutonomousExecutionStateModel":         autonomousExecutionState,
		"ParticipantCrossingPolicyReferenceModel":          crossingPolicyReference,
		"ParticipantInjectContentModel":                    participantInjectContent,
		"ParticipantOpacityRuntimeEnforcementBindingModel": opacityEnforcementBinding,
		"ProcessResourceLimitCapabilityModel":              processResourceLimitCapability,
		"RealizationKeyedCollectionConstraint":             keyedCollectionConstraint,
		"RealizationCollection":                            collectionMembers,
		"RealizationSequenceConstraint":                    func(v any) error { return require(itemBounds(v)) },
		"RealizationSupportDeclarationModel":               realizationSupportDeclaration,
		"ResolvedImportProvenance":                         resolvedImportProvenance,
		"ResolvedRealizationAuthorityModel":                func(v any) error { return require(uniqueRows(at(v, "bounds"), "identity_digest", "value_pointer")) },
		"TrialProcessorPlanReferenceModel":                 processorPlanReference,
		"VersionDomain":                                    versionDomainModel,
	}
	return rules
}

// referenceKind checks an experiment reference kind and an optional digest pin.
func referenceKind(v any, kind string, digest bool) bool {
	return stringAt(v, fieldRefKind) == kind && (!digest || at(v, "ref_digest") != nil)
}

func uniqueRows(rows any, fields ...string) bool {
	return len(rowTupleSet(rows, fields...)) == len(array(rows))
}

func participantManifestKeys(v any) bool {
	return uniqueRows(at(v, "participant_manifest_refs"), fieldParticipantAddress, "implementation_name", "implementation_version", "manifest_version")
}

func apparatusBindingModel(v any) error {
	if !participantManifestKeys(v) {
		return invalid()
	}
	for _, reference := range array(at(v, "manifest_refs")) {
		if at(reference, "ref_digest") == nil {
			return invalid()
		}
	}
	return nil
}

func mixedCompositionBindingModel(v any) error {
	profile := at(v, "profile_ref")
	return require(referenceKind(profile, termProfile, true) && at(profile, fieldRefVersion) != nil && at(profile, "ref_path") == nil && participantManifestKeys(v))
}

func trialInputRefsModel(v any) error {
	if !referenceKind(at(v, "authoring_input_ref"), termAuthoringInput, true) {
		return invalid()
	}
	for _, reference := range array(at(v, "capture_spec_refs")) {
		if !referenceKind(reference, termCaptureSpec, true) {
			return invalid()
		}
	}
	if !uniqueRows(at(v, "capture_spec_refs"), fieldRefID, fieldRefVersion) {
		return invalid()
	}
	for _, field := range []string{"binding_descriptor_set_ref", "associated_artifact_set_ref"} {
		if reference := at(v, field); reference != nil && !referenceKind(reference, termOther, true) {
			return invalid()
		}
	}
	if study := at(v, "study_ref"); study != nil && !referenceKind(study, kindStudy, false) {
		return invalid()
	}
	for _, reference := range array(at(v, "mixed_composition_profile_refs")) {
		if !referenceKind(reference, termProfile, true) || at(reference, "ref_path") != nil {
			return invalid()
		}
	}
	return require(uniqueRows(at(v, "mixed_composition_profile_refs"), fieldRefID, fieldRefVersion))
}

func controlKinds(references any, kind string) bool {
	for _, reference := range array(references) {
		if stringAt(reference, termKind) != kind {
			return false
		}
	}
	return true
}

func controlProfileObligation(v any) error {
	if stringAt(v, termProfile, termKind) != termProfile {
		return invalid()
	}
	if err := controlResultSlot(v); err != nil {
		return err
	}
	support := at(v, "admitted_support")
	if !uniqueRows(support, "instance_id") {
		return invalid()
	}
	for _, item := range array(support) {
		if stringAt(item, "status") != termResolved || stringAt(item, "effective_level") == statusUnsupported {
			return invalid()
		}
	}
	return nil
}

// controlResultSlot checks the constraint kinds and the constraints of a
// bounded strength.
func controlResultSlot(v any) error {
	constraints := at(v, termConstraints)
	return require(controlKinds(constraints, termConstraint) && (stringAt(v, "required_strength") != assuranceBounded || len(array(constraints)) > 0))
}

// evidenceEnumerations lists the members of each enumerated evidence field.
// A member is matched after case folding, with a hyphen read as an underscore.
// A whole-field variable reference is also permitted.
func evidenceEnumerations() map[string][]string {
	return map[string][]string{
		"source_class":    {"scenario_native_observability", "participant_action", "participant_observation", "scenario_state", "processor_backend", "apparatus", "external", termOther},
		"channel":         {"packet_capture", "log", "trace", "metric", "file_artifact", "screen_capture", "api_response", "database_record", "participant_output", termOther},
		"redaction":       {"none", "redact_sensitive", "redact_secrets", "aggregate_only", "derived_only", termOther},
		"integrity":       {"none", "checksum", "signature", "chain_of_custody", "timestamped", termOther},
		"retention":       {"not_retained", "run_lifetime", "study_lifetime", "archival", "policy_defined", termOther},
		"loss_disclosure": {"not_expected", "best_effort", "required", termOther},
	}
}

func evidenceRequirementModel(v any) error {
	if !evidenceTerms(v) || !evidenceLists(v) {
		return invalid()
	}
	present := func(field string) bool { return stringAt(v, field) != "" }
	listed := func(field string) bool { return len(array(at(v, field))) > 0 }
	if !listed("source_refs") && at(v, "source_class") == nil || !listed(termScopeRefs) && !present("scope") {
		return invalid()
	}
	if !present("window") && !present("trigger_ref") && !present("boundary_ref") && !present("boundary_kind") {
		return invalid()
	}
	if at(v, "channel") == nil && !listed("channel_refs") && !present("boundary_kind") {
		return invalid()
	}
	if present("output_contract") != listed("field_selectors") || present("capture_spec_ref") != present("capture_requirement_ref") {
		return invalid()
	}
	return mediaDeclaration(stringAt(v, "output_contract"), stringsOf(at(v, "media_types")))
}

// evidenceTerms reports whether each enumerated evidence field holds a member
// or a whole-field variable reference.
func evidenceTerms(v any) bool {
	for field, members := range evidenceEnumerations() {
		value, present := object(v)[field]
		term, ok := value.(string)
		if !present || value == nil || ok && variableRef(term) {
			continue
		}
		if !ok || !slices.Contains(members, strings.ReplaceAll(strings.ToLower(term), "-", "_")) {
			return false
		}
	}
	return true
}

// evidenceLists reports whether each evidence list has unique, non-blank
// members and whether each field selector is a canonical JSON Pointer.
func evidenceLists(v any) bool {
	for _, field := range []string{"source_refs", termScopeRefs, "channel_refs", "media_types", "field_selectors", "notes"} {
		values := stringsOf(at(v, field))
		if !unique(values) || slices.ContainsFunc(values, sdlBlank) {
			return false
		}
	}
	return !slices.ContainsFunc(stringsOf(at(v, "field_selectors")), func(selector string) bool { return !canonicalPointer(selector) })
}

// domainDescriptorModel checks a domain whose kind defaults to the
// definition's kind.
func domainDescriptorModel(kind string) func(any) error {
	return func(v any) error {
		value := maps.Clone(object(v))
		if _, present := value[termKind]; !present {
			value[termKind] = kind
		}
		descriptor, err := envelopeDomain(value)
		return require(err == nil && descriptor.Validate() == nil)
	}
}

func autonomousExecutionState(v any) error {
	attempted, ok := defaultNumber(v, "attempted_actions", 0)
	succeeded, sok := defaultNumber(v, "succeeded_actions", 0)
	failed, fok := defaultNumber(v, "failed_actions", 0)
	retry, rok := defaultNumber(v, "current_retry", 0)
	if !ok || !sok || !fok || !rok || new(big.Rat).Add(succeeded, failed).Cmp(attempted) > 0 || retry.Cmp(attempted) > 0 {
		return invalid()
	}
	if !fieldsUnique(v, "completed_candidate_ids") {
		return invalid()
	}
	random := 0
	for _, field := range []string{"random_control_id", "random_profile_id", "random_namespace"} {
		if stringAt(v, field) != "" {
			random++
		}
	}
	if text(defaultMember(v, termProfile, termAutonomousExecutionV1)) == termAutonomousExecutionV1 {
		return require(random == 0)
	}
	return require(random == 3)
}

func crossingPolicyReference(v any) error {
	from, fromOK := number(at(v, "valid_from_order"))
	until, untilOK := number(at(v, "valid_until_order"))
	effective, effectiveOK := number(at(v, fieldEffectiveOrder))
	return require(fromOK && untilOK && effectiveOK && until.Cmp(from) >= 0 && effective.Cmp(from) >= 0 && effective.Cmp(until) <= 0)
}

func opacityEnforcementBinding(v any) error {
	claim := at(v, "claim")
	scope := stringAt(claim, "quantifier_scope")
	if !equal(at(claim, "assurance_axis"), at(v, "assurance_axis")) || stringAt(claim, "assurance_status") != assuranceEnforced || stringAt(claim, "evidence_scope") != evidenceFinite {
		return invalid()
	}
	return require(scope == "single-artifact" || scope == "finite-cases")
}

func processResourceLimitCapability(v any) error {
	if at(v, "maximum") == nil {
		return nil
	}
	minimum, minOK := defaultNumber(v, "minimum", 0)
	maximum, maxOK := number(at(v, "maximum"))
	return require(minOK && maxOK && maximum.Cmp(minimum) >= 0)
}

// keyedCollectionConstraint checks identity arity, member and alias
// identities, and alias targets.
func keyedCollectionConstraint(v any) error {
	arity := len(array(at(v, "identity_fields")))
	if !fieldsUnique(v, "identity_fields") || !itemBounds(v) {
		return invalid()
	}
	members, ok := identityKeys(at(v, "members"), "identity", arity)
	if !ok || len(members) != len(array(at(v, "members"))) {
		return invalid()
	}
	aliases, ok := identityKeys(at(v, "aliases"), "identity", arity)
	if !ok || len(aliases) != len(array(at(v, "aliases"))) {
		return invalid()
	}
	targets, ok := identityKeys(at(v, "aliases"), "target", arity)
	if !ok {
		return invalid()
	}
	for key := range aliases {
		if members[key] {
			return invalid()
		}
	}
	for key := range targets {
		if !members[key] {
			return invalid()
		}
	}
	return nil
}

// collectionMembers requires a semantic identity digest as each member key.
func collectionMembers(v any) error {
	for key := range object(at(v, "members")) {
		if !strings.HasPrefix(key, digest.Prefix) || !digest.Valid(key) || strings.ToLower(key) != key {
			return invalid()
		}
	}
	return nil
}

// identityKeys returns the canonical identity keys of the rows. It reports
// false when a row identity has the wrong arity.
func identityKeys(rows any, field string, arity int) (map[string]bool, bool) {
	keys := map[string]bool{}
	for _, row := range array(rows) {
		identity := array(at(row, field))
		key, err := jsonDigest(identity)
		if len(identity) != arity || err != nil {
			return nil, false
		}
		keys[key] = true
	}
	return keys, true
}

// itemBounds checks min_items against max_items with their defaults.
func itemBounds(v any) bool {
	low, lowOK := defaultNumber(v, "min_items", 0)
	high, highOK := defaultNumber(v, "max_items", maxCollectionItems)
	return lowOK && highOK && low.Cmp(high) <= 0
}

func realizationSupportDeclaration(v any) error {
	if !uniqueRows(at(v, "process_resource_limits"), "resource") {
		return invalid()
	}
	identities := map[string]bool{}
	for _, capability := range array(at(v, "artifact_mechanisms")) {
		mechanism := at(capability, "mechanism")
		key, err := jsonDigest([]any{at(mechanism, "mechanism"), at(mechanism, termProfile), at(mechanism, "version"), at(mechanism, "digest")})
		if err != nil || identities[key] {
			return invalid()
		}
		identities[key] = true
	}
	return nil
}

func versionDomainModel(v any) error {
	_, err := modelVersionDomain(v)
	return require(err == nil)
}
func modelVersionDomain(v any) (softwareversion.Domain, error) {
	relation := at(v, "relation")
	bound := func(field string) *string {
		if at(v, field) == nil {
			return nil
		}
		value := stringAt(v, field)
		return &value
	}
	identity := softwareversion.Relation{Authority: stringAt(relation, termAuthority), ID: stringAt(relation, "contract_id"), Revision: stringAt(relation, termRevision), Digest: stringAt(relation, "digest")}
	return softwareversion.NewDomain(identity, bound("lower"), bound("upper"), boolean(defaultMember(v, "lower_closed", true)), boolean(defaultMember(v, "upper_closed", true)))
}
