package processor

// Shared vocabulary for the admitted processor wire projections.
const (
	termUnknown                          = "unknown"
	termAccountPlacement                 = "account-placement"
	termAccounts                         = "accounts"
	termAction                           = "action"
	termActionContract                   = "action-contract"
	termActionContracts                  = "action_contracts"
	termAddress                          = "address"
	termAssertion                        = "assertion"
	termBackendLog                       = "backend-log"
	termBehaviorSpecification            = "behavior-specification"
	termCall                             = "call"
	termCompute                          = "compute"
	termConditionBinding                 = "condition-binding"
	termConditions                       = "conditions"
	termContentPlacement                 = "content-placement"
	termDecision                         = "decision"
	termDisabled                         = "disabled"
	termDomainControllerPlacement        = "domain-controller-placement"
	termEvaluation                       = "evaluation"
	termEvent                            = "event"
	termExact                            = "exact"
	termFeatures                         = "features"
	termGeneratedArtifact                = "generated-artifact"
	termInject                           = "inject"
	termInjectBinding                    = "inject-binding"
	termLog                              = "log"
	termNetwork                          = "network"
	termNode                             = "node"
	termNodes                            = "nodes"
	termNone                             = "none"
	termNull                             = "null"
	termObservationBoundary              = "observation-boundary"
	termOrchestration                    = "orchestration"
	termOutcomeInterpretationRule        = "outcome-interpretation-rule"
	termParticipant                      = "participant"
	termParticipantAutonomousExecutionV3 = "participant-autonomous-execution/v3"
	termParticipantBehavior              = "participant-behavior"
	termPersistentVolume                 = "persistent-volume"
	termProvisioning                     = "provisioning"
	termRetry                            = "retry"
	termRedacted                         = "redacted"
	termScript                           = "script"
	termSelf                             = "self"
	termStory                            = "story"
	termSwitch                           = "switch"
	termToolAffordances                  = "tool_affordances"
)

const (
	termAssertions             = "assertions"
	termBehaviorSpecifications = "behavior_specifications"
	termContent                = "content"
	termControl                = "control"
	termDescription            = "description"
	termEvents                 = "events"
	termFileArtifact           = "file-artifact"
	termInjects                = "injects"
	termObjective              = "objective"
	termObservation            = "observation"
	termObservationBoundaries  = "observation_boundaries"
	termProposition            = "proposition"
	termProvision              = "provision"
	termWorkflow               = "workflow"
)

const (
	termGeneratedArtifacts = "generated_artifacts"
	termObjectives         = "objectives"
	termOther              = "other"
	termParallel           = "parallel"
	termPersistentVolumes  = "persistent_volumes"
	termProposal           = "proposal"
)

const (
	termTrace                      = "trace"
	termScripts                    = "scripts"
	termPropositions               = "propositions"
	termOutcomeInterpretationRules = "outcome_interpretation_rules"
)

const termStories = "stories"

const termWorkflows = "workflows"

const (
	termScalarString   = "string"
	termScalarInteger  = "integer"
	termScalarBoolean  = "boolean"
	termFailed         = "failed"
	termPartialSuccess = "partial_success"
	termError          = "error"
	termPythonNone     = "None"
	termCadenceWaiting = "cadence_waiting"
	termReplay         = "replay"
)

const (
	termSucceeded   = "succeeded"
	termDwellActive = "dwell_active"
)

const termReset = "reset"

const (
	termObservationEmitted      = "observation_emitted"
	termActionAttempted         = "action_attempted"
	termStateTransitionRecorded = "state_transition_recorded"
	termAccepted                = "accepted"
	termReplayBoundary          = "replay_boundary"
	termDisclosedRefs           = "disclosed_refs"
	termDisclosed               = "disclosed"
)

const termVisibleRefs = "visible_refs"
