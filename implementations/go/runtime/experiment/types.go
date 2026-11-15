// Package experiment coordinates admitted trials through installed shared-runtime owners.
package experiment

import (
	"context"
	"encoding/json"
	"io"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

// Identity binds a concrete actor to its admitted scopes.
type Identity struct {
	ActorID            string
	AuthorizationScope []string
}

// Trial binds one deterministic attempt to its admitted plan and realization.
type Trial struct {
	Identity                               Identity
	Plan                                   binding.AdmittedTrialPlanV1
	PlanEntryID, RunID, ExecutionAttemptID string
	Attempt                                int
	StartedAt, Deadline                    string
	Realization                            trial.Realization
}

// Observation reports verified phase facts; retry readiness uses Reusable.
type Observation struct {
	Kind, State                                                  string
	Ceased, EffectsAbsent, Complete, Reusable, IdempotentEffects bool
	Configurations                                               []binding.ParticipantConfigurationResultV1
	Evidence                                                     []binding.ExperimentEvidenceRecordV1
	CleanupEvidence                                              []binding.ExperimentEvidenceRecordV1
	CleanupReceipt                                               *binding.TrialCleanupReceiptV1
	VerifiedCompensations                                        []string
	ObligationResults                                            map[string]admission.Fragment
	Snapshot                                                     binding.RuntimeSnapshotV1
	OperationReceipts                                            []binding.OperationReceiptV1
}

// Phase separates shared-engine progress from verified observations.
// Pending observations remain facts; they do not complete the underlying phase.
type Phase struct {
	State       string
	Observation *Observation
}

// Host forwards phases to the shared runtime. Mutations reconcile the deterministic
// attempt and phase before dispatch; unknown effects cannot be blindly repeated.
//
//nolint:interfacebloat // One installed runtime owner must reconcile both control phases and their verified facts.
type Host interface {
	Records(ctx context.Context, trial Trial) (RecordSource, error)
	Authorize(ctx context.Context, identity Identity, experimentID string) error
	Admit(ctx context.Context, trial Trial) (string, error)
	Configure(ctx context.Context, trial Trial) (Phase, error)
	Advance(ctx context.Context, trial Trial) (Phase, error)
	Observe(ctx context.Context, trial Trial) (Observation, error)
	Capture(ctx context.Context, trial Trial) (Phase, error)
	Cleanup(ctx context.Context, trial Trial, reason string) (Phase, error)
	Stop(ctx context.Context, trial Trial, reason string) (Phase, error)
	Cancel(ctx context.Context, trial Trial) error
	Retire(ctx context.Context, trial Trial) error
	IsRetired(ctx context.Context, trial Trial) (bool, error)
	PrepareRetry(ctx context.Context, trial Trial) (Phase, error)
	Verify(ctx context.Context, trial Trial, observation Observation) error
}

// Decision is an immutable record minted only by this native owner.
type Decision interface {
	ID() string
	SchemaVersion() string
	JSON() []byte
	experimentDecision()
}

// Journal atomically claims decision IDs and rejects changed content at an existing ID.
type Journal interface {
	Load(ctx context.Context) ([]Decision, error)
	Claim(ctx context.Context, decision Decision) (bool, error)
}

// OwnerCalls supplies the shared bounded adapter and retains workers until they drain.
type OwnerCalls interface {
	Call(ctx context.Context, lane string, budget time.Duration, work func(context.Context) (any, error)) (any, error)
}

// Options requires explicit host, journal and bounded-call owners.
type Options struct {
	Inputs                                        trial.RealizationInputs
	Identity                                      Identity
	Host                                          Host
	Journal                                       Journal
	Calls                                         OwnerCalls
	Clock                                         clock.Clock
	AdmissionBudget, ExecutionBudget, StoreBudget time.Duration
	Replacement                                   *trial.Request
	Archive                                       Archive
}

// Progress reports one bounded coordinator transition.
type Progress struct {
	ExperimentID, State             string
	PlanEntryID, ExecutionAttemptID *string
}

// Coordinator owns actor-bound experiment progress and record production.
type Coordinator interface {
	Advance(ctx context.Context, identity Identity) (Progress, error)
	Cancel(ctx context.Context, identity Identity) error
	Results(ctx context.Context, identity Identity) ([]Observation, error)
	Records(ctx context.Context, identity Identity, options RecordOptions) (RecordBundle, error)
	experimentCoordinator()
}

// RunMetadata supplies scientific facts without inferring them from execution.
type RunMetadata struct {
	RunVersion, OutcomeStatus                                                  string
	ApparatusContext                                                           *binding.ExperimentApparatusContextV1
	ParticipantImplementationProvenance, Traceability, Invalidation            json.RawMessage
	RealizedBindings, ParameterSet, EvidenceArtifacts, RealizedFormDisclosures []json.RawMessage
	ResultSummaries                                                            map[string]json.RawMessage
}

// RecordSource keeps retained starts, observations and detached shared-host operation facts.
type RecordSource struct {
	RunID                        string
	Plan                         binding.AdmittedTrialPlanV1
	Realization                  trial.Realization
	Attempts, Observations       []Decision
	ExecutionSnapshots           map[string]binding.RuntimeSnapshotV1
	PhaseStates, OperationStates map[string]string
	OperationRefs                map[string][]string
	OperationReceipts            []binding.OperationReceiptV1
}

// Accounting separates planned, started, resolved and scientifically eligible populations.
type Accounting struct {
	PlannedRuns, StartedRuns, UnstartedRuns, ResolvedRuns, UnresolvedRuns int
	Attempts, RetryAttempts, ReplacementRuns                              int
	RunOutcomes, ScientificOutcomes, ExecutionOutcomes, CaptureOutcomes   map[string]int
	CleanupOutcomes, ValidationOutcomes                                   map[string]int
	MetricPopulations                                                     map[string]map[string]int
}

// RecordBundle preserves current records, immutable history and validation dispositions.
type RecordBundle struct {
	Runs, RetainedHistory, ValidationRecords []binding.ExperimentRunV1
	Sources                                  []RecordSource
	Accounting                               Accounting
	ValidationByRun                          map[string]string
	ValidationFailures                       map[string][]string
	EligibleRunIDs                           []string
	Study                                    *binding.ExperimentStudyV1
	StudyValidation                          string
}

// EvidenceInputs transfers authorized streams and their reader ownership.
type EvidenceInputs struct {
	Inputs  admission.ExperimentEvidenceInputs
	Readers []io.Closer
}

// EvidenceReader opens fresh authorized evidence for one immutable run version.
type EvidenceReader interface {
	Open(ctx context.Context, run binding.ExperimentRunV1) (EvidenceInputs, error)
}

// Archive builds scientific runs and publishes immutable artifacts with exact readback.
type Archive interface {
	BuildRun(ctx context.Context, source RecordSource) (binding.ExperimentRunV1, error)
	WriteSources(ctx context.Context, source RecordSource) error
	WriteRun(ctx context.Context, run binding.ExperimentRunV1) error
	ReadRun(ctx context.Context, runID, version string) (binding.ExperimentRunV1, error)
	WriteStudy(ctx context.Context, study binding.ExperimentStudyV1) error
	ReadStudy(ctx context.Context, studyID, version string) (binding.ExperimentStudyV1, error)
}

// RecordOptions supplies explicit metadata, evidence and publication owners.
type RecordOptions struct {
	Metadata map[string]RunMetadata
	Study    *binding.ExperimentStudyV1
	Evidence EvidenceReader
	Archive  Archive
}
