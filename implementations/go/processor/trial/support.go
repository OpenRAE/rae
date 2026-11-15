package trial

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func admitEntrySupport(request Request, input compilationInputs, selected sdl.InstantiatedScenario, backend binding.BackendManifestV2) error {
	capture, err := captureInputs(request, input)
	if err != nil {
		return err
	}
	compiled, err := processor.CompileWithOptions(selected, processor.CompileOptions{Capture: capture})
	if err != nil {
		return err
	}
	if err = admitToolSupport(compiled.Model(), input.manifests, backend); err != nil {
		return err
	}
	result, err := planning.PlanWithManifest(compiled, backend, planning.Options{RealizationEnvelope: &input.envelope})
	if err != nil {
		return err
	}
	failures := []diagnostic.Diagnostic{}
	for _, d := range result.Diagnostics {
		if d.Domain == "capture" {
			failures = append(failures, d)
		}
	}
	if len(failures) > 0 {
		return &captureAdmissionError{diagnostics: failures}
	}

	return nil
}

func admitToolSupport(model processor.RuntimeModel, manifests map[ApparatusManifestKey]admission.ApparatusManifest, backend binding.BackendManifestV2) error {
	selected := false
	for _, manifest := range manifests {
		if manifest.Processor == nil {
			continue
		}
		selected = true
		support, checkErr := processor.ParticipantSupport(model, backend, manifest.Processor)
		if checkErr != nil {
			return checkErr
		}
		if len(support.Tools) > 0 {
			return refuse("tool-support-insufficient", "/apparatus/manifest_refs", "A selected apparatus lacks required tool-profile support or capacity.")
		}
	}

	if selected {
		return nil
	}
	support, err := processor.ParticipantSupport(model, backend, nil)
	if err != nil {
		return err
	}
	if len(support.Tools) > 0 {
		return refuse("tool-support-apparatus-missing", "/apparatus/manifest_refs", "Tool profiles require selected processor and backend declarations.")
	}
	return nil
}

type cleanupRequirements struct {
	CleanState struct {
		Mode   string   `json:"mode"`
		Probes []string `json:"verification_probe_refs"`
	} `json:"clean_state"`
	Obligations map[string]struct {
		Action      string   `json:"action_kind"`
		Requirement string   `json:"requirement"`
		Probes      []string `json:"verification_probe_refs"`
	} `json:"cleanup_obligations"`
	Retry struct {
		Attempts    int    `json:"max_attempts"`
		AfterEffect string `json:"after_effect_policy"`
	} `json:"retry_policy"`
}

type cleanupSupport struct {
	Actions  []string `json:"supported_action_kinds"`
	Methods  []string `json:"supported_verification_methods"`
	Reusable bool     `json:"supports_reusable_state"`
	Residual bool     `json:"supports_residual_state_disclosure"`
}

type operationSupervision struct {
	Guarantees []string `json:"guarantees"`
}

type backendTrialCapabilities struct {
	Cleanup     *cleanupSupport       `json:"cleanup"`
	Supervision *operationSupervision `json:"operation_supervision"`
}

func admitTrialControls(backend binding.BackendManifestV2, controls executionControls, template cleanupTemplate) error {
	raw, err := encoded(backend)
	if err != nil {
		return err
	}
	var manifest struct {
		Capabilities backendTrialCapabilities `json:"capabilities"`
	}
	if decode(raw, &manifest) != nil {
		return trialInvalid()
	}
	raw, err = encoded(template)
	if err != nil {
		return err
	}
	var requirements cleanupRequirements
	if decode(raw, &requirements) != nil {
		return trialInvalid()
	}
	if err = admitCleanupSupport(manifest.Capabilities.Cleanup, requirements); err != nil {
		return err
	}
	guarantees := []string{}
	if manifest.Capabilities.Supervision != nil {
		guarantees = manifest.Capabilities.Supervision.Guarantees
	}
	if controls.OnTimeout == "cancel" && !slices.Contains(guarantees, "cancellation") {
		return unsupportedTrialControl()
	}
	if requirements.Retry.Attempts > 1 && (!slices.Contains(guarantees, "cessation-evidence") || requirements.Retry.AfterEffect == "disallow" && !slices.Contains(guarantees, "effect-observation")) {
		return unsupportedTrialControl()
	}
	return nil
}

func unsupportedTrialControl() error {
	return refuse("execution-authority-unsupported", "/execution_authority", "a selected backend cannot honour the admitted execution authority")
}
func admitCleanupSupport(cleanup *cleanupSupport, requirements cleanupRequirements) error {
	if cleanup == nil {
		return unsupportedTrialControl()
	}
	probes := slices.Clone(requirements.CleanState.Probes)
	for _, obligation := range requirements.Obligations {
		if obligation.Requirement != "required" {
			continue
		}
		if !slices.Contains(cleanup.Actions, obligation.Action) || !cleanup.Residual {
			return unsupportedTrialControl()
		}
		probes = append(probes, obligation.Probes...)
	}
	for _, probe := range probes {
		method, _, _ := strings.Cut(probe, ":")
		if !slices.Contains(cleanup.Methods, method) {
			return unsupportedTrialControl()
		}
	}
	if requirements.CleanState.Mode == termDeclaredReusable && !cleanup.Reusable {
		return unsupportedTrialControl()
	}
	return nil
}
func trialIngress() ingress.Limits { return ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64} }
