package trial

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type compilationRefusalError struct{ code, address, message string }

func (r *compilationRefusalError) Error() string { return r.code }
func refuse(code, address, message string) error {
	return &compilationRefusalError{code, address, message}
}

// Compile returns a complete sealed plan or safe domain diagnostics.
func Compile(request Request) (Result, error) { return CompileContext(context.Background(), request) }

// CompileContext also passes cancellation to installed owner validators.
func CompileContext(ctx context.Context, request Request) (Result, error) {
	if request.Limits == (Limits{}) {
		request.Limits = DefaultLimits()
	}
	if request.MixedCompositionLimits == (MixedCompositionLimits{}) {
		request.MixedCompositionLimits = DefaultMixedCompositionLimits()
	}
	if err := ctx.Err(); err != nil {
		return Result{}, err
	}
	plan, err := compilePlan(ctx, request)
	if err == nil {
		return Result{Plan: &plan, Diagnostics: []diagnostic.Diagnostic{}}, nil
	}
	if capture, ok := errors.AsType[*captureAdmissionError](err); ok {
		return Result{Diagnostics: capture.diagnostics}, nil
	}
	var refusal *compilationRefusalError
	if !errors.As(err, &refusal) {
		category, known := fault.CategoryOf(err)
		if !known || category != fault.InvalidInput {
			return Result{}, err
		}
		refusal = &compilationRefusalError{"input-invalid", "", "trial compilation input failed closed validation"}
	}
	return Result{Diagnostics: []diagnostic.Diagnostic{{Code: "trial-compiler." + refusal.code, Domain: compilerDomain, Address: refusal.address, Message: refusal.message, Severity: "error"}}}, nil
}

type compilationInputs struct {
	participants                           map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1
	descriptors                            []admittedDescriptor
	owner                                  *admission.Validator
	spec                                   experimentSpec
	refs                                   inputReferences
	refsJSON, authorityJSON, apparatusJSON json.RawMessage
	authority                              executionAuthority
	family                                 struct {
		Name   string                     `json:"name"`
		Points map[string]json.RawMessage `json:"variation_points"`
		// Parallelism is the family's authored trial_parallelism; the plan seals it unchanged.
		Parallelism json.RawMessage `json:"trial_parallelism"`
	}
	envelope      binding.RealizationEnvelopeV1
	backends      map[ApparatusManifestKey]binding.BackendManifestV2
	manifests     map[ApparatusManifestKey]admission.ApparatusManifest
	mixed         map[string]mixedAuthority
	mixedProfiles map[string]mixedProfile
}

func compilerProfiles(spec experimentSpec, mixed, replacement bool) (json.RawMessage, error) {
	profile := compilerDomain
	if replacement {
		profile += "-replacement"
	}
	if !isNull(spec.Factorial) || !isNull(spec.RunPlan.AllocationPolicy) {
		profile += "-designed"
	}
	if mixed {
		profile += "-mixed-composition"
	}
	profile += "-v1"
	entry, run := "trial-entry-identity-v1", "archival-run-identity-v1"
	if mixed {
		entry, run = "trial-entry-identity-mixed-composition-v1", "archival-run-identity-mixed-composition-v1"
	}
	profiles := map[string]string{"coordinate_profile": "trial-coordinate-v1", "entry_identity_profile": entry, "run_identity_profile": run, "canonicalization_profile": "jcs-sha256-v1", "integrity_profile": "acyclic-digest-chain-v1", "compiler_profile": profile, "selection_policy_profile": "experiment-selection-v1", "random_stream_profile": "blake3-xof-v1", "execution_control_profile": "attempt-control-v1", "cleanup_profile": "trial-cleanup-v1"}
	if !isNull(spec.Factorial) {
		var design struct {
			Profile string `json:"profile"`
		}
		if decode(spec.Factorial, &design) != nil {
			return nil, trialInvalid()
		}
		if design.Profile == profileFactorialTreatments {
			profiles["treatment_profile"] = design.Profile
		}
	}
	if !isNull(spec.RunPlan.AllocationPolicy) {
		profiles["allocation_profile"] = "fisher-yates-allocation-v1"
	}
	return encoded(profiles)
}

type cleanupTemplate struct {
	CleanState  json.RawMessage `json:"clean_state"`
	Boundaries  json.RawMessage `json:"resource_boundaries"`
	Obligations json.RawMessage `json:"cleanup_obligations"`
	Retry       json.RawMessage `json:"retry_policy"`
}
type boundCleanup struct {
	cleanupTemplate

	SchemaVersion string `json:"schema_version"`
	ID            string `json:"plan_id"`
	EntryID       string `json:"plan_entry_id"`
	RunID         string `json:"run_id"`
}
