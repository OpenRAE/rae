package admission

const (
	codeContractCatalogInvalid    = "contract-catalog-invalid"
	manifestV2Suffix              = "-manifest/v2"
	parentAdmittedMarker          = "@parent-admitted"
	reasonEffectConflict          = "effect-conflict"
	codeContractTime              = "contract-time"
	schemaDefinitionsPrefix       = "#/$defs/"
	traceImportedAssertion        = "imported-assertion"
	traceTransformationAssumption = "transformation-assumption"
)

// Published terms shared by the family validators.
const (
	outcomeSuccess        = "success"
	notApplicable         = "not-applicable"
	kindProcessor         = "processor"
	kindBackend           = "backend"
	dispositionAccepted   = "accepted"
	kindRun               = "run"
	strengthEvidence      = "evidence_backed"
	strengthFalsification = "falsification_backed"
)

const (
	kindScenario                  = "scenario"
	conditionFixed                = "fixed"
	kindStudy                     = "study"
	retryDisallow                 = "disallow"
	strengthSemantic              = "semantic"
	responseNewTrial              = "new-trial"
	fieldPlane                    = "plane"
	kindParticipantImplementation = "participant-implementation"
)

const (
	kindTask      = "task"
	fieldTargetID = "target_id"
)

const (
	outcomeFailed       = "failed"
	outcomeSucceeded    = "succeeded"
	requirementRequired = "required"
	retryReset          = "reset"
	resultNotTriggered  = "not-triggered"
)

const (
	outcomeRefused             = "refused"
	fieldSubjectAssertionID    = "subject_assertion_id"
	contributionAuthorDecision = "author-decision"
)

const contributionPolicyDecision = "governed-policy-decision"

const (
	fieldLeftCarrierRef           = "left_carrier_ref"
	crossingMultiKind             = "participant-crossing-multi-dpbb/v1"
	crossingKind                  = "participant-crossing-dpbb/v1"
	assuranceModelChecked         = "model-checked"
	assuranceBounded              = "bounded"
	assuranceEnforced             = "enforced"
	assuranceDeclared             = "declared"
	evidenceModelCheck            = "model-check"
	assuranceConformant           = "conformant"
	strengthStructural            = "structural"
	evidenceFinite                = "finite"
	statusImplemented             = "implemented"
	statusPartial                 = "partial"
	contributionInferredStructure = "inferred-structure"
	assuranceRealized             = "realized"
	evidenceProof                 = "proof"
	statusFuture                  = "future"
)

const (
	fieldObservationProjectionRef = "observation_projection_ref"
	assuranceProved               = "proved"
)

const (
	fieldObservationProjectionRevision = "observation_projection_revision"
	sensitivitySecret                  = "secret"
	fieldEpisodeID                     = "episode_id"
	fieldParticipantAddress            = "participant_address"
)

const (
	statusVerified           = "verified"
	scopeResources           = "resources"
	messageOutcome           = "outcome"
	messageControl           = "control"
	statusUnknown            = "unknown"
	effectAbsent             = "absent"
	outcomeIndeterminate     = "indeterminate"
	fieldRelationID          = "relation_id"
	statusTested             = "tested"
	outcomeFailure           = "failure"
	sideAfter                = "after"
	statusComplete           = "complete"
	fieldWorkflowAddress     = "workflow_address"
	placementSchedule        = "schedule"
	injectApplied            = "effect-applied"
	injectAbsent             = "effect-absent"
	contractInjectOccurrence = "inject-occurrence-v1"
	fieldStrategyRef         = "strategy_ref"
	outcomeCounterexample    = "counterexample-found"
	fieldAssumptions         = "assumptions"
	classificationExcluded   = "excluded"
)

const (
	messageReconciliation = "reconciliation"
	fieldTaxonomyID       = "taxonomy_id"
	fieldTaxonomyRevision = "taxonomy_revision"
	sideBefore            = "before"
	statusUnsupported     = "unsupported"
	classificationWitness = "witness"
)

const (
	statusInProgress               = "in-progress"
	statusRunning                  = "running"
	outcomeAborted                 = "aborted"
	statusSuperseded               = "superseded"
	postureExact                   = "exact"
	outcomeCancelled               = "cancelled"
	fieldEvidenceRefs              = "evidence_refs"
	basisObserved                  = "observed"
	kindRecursiveRecord            = "recursive-record"
	postureNone                    = "none"
	typeBoolean                    = "boolean"
	outcomeVacuous                 = "vacuous-secret-domain"
	fieldRefID                     = "ref_id"
	kindScenarioSnapshot           = "scenario-snapshot"
	kindApparatusContext           = "apparatus-context"
	kindMaterializationAttestation = "materialization-attestation"
	fieldMappings                  = "mappings"
	fieldGeneratedArtifacts        = "generated_artifacts"
	kindDeadline                   = "deadline"
)

const (
	fieldRefKind             = "ref_kind"
	fieldRefVersion          = "ref_version"
	fieldProgressionPolicies = "progression_policies"
)

const (
	termActive                                  = "active"
	termAuthoringInput                          = "authoring-input"
	termAuthority                               = "authority"
	termDeclassification                        = "declassification"
	termDelivered                               = "delivered"
	termDisclosed                               = "disclosed"
	termDisclosedWeak                           = "disclosed_weak"
	termEvent                                   = "event"
	termEvidence                                = "evidence"
	termFactorialTreatmentsV1                   = "factorial-treatments-v1"
	termImplementation                          = "implementation"
	termManifest                                = "manifest"
	termMissed                                  = "missed"
	termParticipantBehaviorHistoryEventStreamV1 = "participant-behavior-history-event-stream-v1"
	termParticipantControlContextAssetV1        = "participant-control-context-asset-v1"
	termParticipantControlContextChangeV1       = "participant-control-context-change-v1"
	termParticipantControlContextRecordV1       = "participant-control-context-record-v1"
	termParticipantOwnerFlowPolicyV1            = "participant-owner-flow-policy-v1"
	termProfile                                 = "profile"
	termRedaction                               = "redaction"
	termRejected                                = "rejected"
	termReported                                = "reported"
	termResolved                                = "resolved"
	termRev1                                    = "rev1"
	termRunID                                   = "run_id"
	termSdlAuthoringInputV1                     = "sdl-authoring-input-v1"
	termSelected                                = "selected"
	termSequencePrefix                          = "sequence_prefix"
	termStratified                              = "stratified"
	termWithheld                                = "withheld"
)

const (
	termItemRef = "item_ref"
)

const (
	termSurfaceID = "surface_id"
)

const (
	termApproval         = "approval"
	termCancellation     = "cancellation"
	termExplicitRequired = "explicit-required"
	termHandoff          = "handoff"
	termProposal         = "proposal"
	termRequiredBindings = "required_bindings"
	termTargetKind       = "target_kind"
)

const (
	termDenial             = "denial"
	termRequiredSelections = "required_selections"
	termTargetRef          = "target_ref"
)

const (
	termDecision              = "decision"
	termExpectedStateRevision = "expected_state_revision"
	termExternalDirection     = "external-direction"
	termFiniteScript          = "finite-script"
	termIntervention          = "intervention"
	termOverride              = "override"
	termRevoked               = "revoked"
	termTargetRevision        = "target_revision"
	termTransitionRef         = "transition_ref"
	termTransitions           = "transitions"
	termValidFromOrder        = "valid_from_order"
)

const (
	termParticipantControlOccurrenceV2 = "participant-control-occurrence-v2"
	termValidUntilOrder                = "valid_until_order"
)

const (
	termAudited     = "audited"
	termDecided     = "decided"
	termDeny        = "deny"
	termPermit      = "permit"
	termRequested   = "requested"
	termTransformed = "transformed"
)

const (
	termTransform = "transform"
)

const (
	termApparatus      = "apparatus"
	termClock          = "clock"
	termConstraint     = "constraint"
	termCrossing       = "crossing"
	termDeliveryRef    = "delivery_ref"
	termPolicy         = "policy"
	termProviderState  = "provider-state"
	termRule           = "rule"
	termState          = "state"
	termTransformation = "transformation"
)

const (
	termApplies = "applies"
	termAttempt = "attempt"
	termOrder   = "order"
	termTrigger = "trigger"
)

const (
	termDelay             = "delay"
	termInject            = "inject"
	termInterrupt         = "interrupt"
	termMask              = "mask"
	termParticipant       = "participant"
	termShutdown          = "shutdown"
	termTeachingInfluence = "teaching-influence"
)

const (
	termReceipt  = "receipt"
	termRoute    = "route"
	termWithhold = "withhold"
)

const (
	termCommitted           = "committed"
	termEffectRequest       = "effect-request"
	termEligible            = "eligible"
	termIndependent         = "independent"
	termRequiredPredecessor = "required-predecessor"
	termSuccessDependent    = "success-dependent"
)

const (
	termBoundedCompatible = "bounded-compatible"
	termOwnerIfcRev1      = "owner-ifc/rev1"
	termStale             = "stale"
	termUnresolved        = "unresolved"
)

const (
	termDisclosedWeakCompatible = "disclosed-weak-compatible"
	termWeakened                = "weakened"
)

const (
	termParticipantControlContextModel   = "ParticipantControlContextModel"
	termParticipantControlRequestModel   = "ParticipantControlRequestModel"
	termParticipantControlRequestV2Model = "ParticipantControlRequestV2Model"
	termApplied                          = "applied"
	termIfcFact                          = "ifc-fact"
	termParticipantBoundaryFlowPolicyV1  = "participant-boundary-flow-policy-v1"
	termParticipantControlEvaluationV2   = "participant-control-evaluation-v2"
)

const (
	termBindings                         = "bindings"
	termParticipantFlowControlRelationV1 = "participant-flow-control-relation-v1"
)

const (
	termAttemptID           = "attempt_id"
	termDecisionID          = "decision_id"
	termDecisionRef         = "decision_ref"
	termDeliveryAttempted   = "delivery-attempted"
	termDerivations         = "derivations"
	termEffects             = "effects"
	termKind                = "kind"
	termParticipantCrossing = "participant-crossing"
	termSatisfied           = "satisfied"
	termSinkDecision        = "sink-decision"
	termTransformationRef   = "transformation_ref"
)

const (
	termLabels = "labels"
)

const (
	termReleases = "releases"
)

const (
	termSinkDecisions = "sink_decisions"
)

const (
	termPhases = "phases"
)

const (
	termAcknowledgement = "acknowledgement"
	termAdmission       = "admission"
	termAllocations     = "allocations"
	termArtifactID      = "artifact_id"
	termDelivery        = "delivery"
	termExecution       = "execution"
	termObservation     = "observation"
	termProgress        = "progress"
)

const (
	termComponents    = "components"
	termContractID    = "contract_id"
	termOwnerReadback = "owner-readback"
)

const (
	termDigest    = "digest"
	termEdges     = "edges"
	termTimeGrant = "time-grant"
)

const (
	termNull    = "null"
	termRemoved = "removed"
)

const (
	termMaterializedScenarioV1 = "materialized-scenario-v1"
)

const (
	termAdded                = "added"
	termBackendRealized      = "backend-realized"
	termEvaluation           = "evaluation"
	termName                 = "name"
	termNode                 = "node"
	termOrchestration        = "orchestration"
	termOrchestrationPlanV1  = "orchestration-plan-v1"
	termOrderingDependencies = "ordering_dependencies"
	termProvisioning         = "provisioning"
)
