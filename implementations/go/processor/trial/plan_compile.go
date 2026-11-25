package trial

import (
	"context"
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type planCompilation struct {
	request      Request
	input        compilationInputs
	replacement  *replacementContext
	coordinates  []coordinate
	rows         []selectionRow
	plan         trialPlan
	signatures   map[string]string
	usedControls map[string]bool
}

func compilePlan(ctx context.Context, request Request) (binding.AdmittedTrialPlanV1, error) {
	return compilePlanWithReplacement(ctx, request, nil)
}
func compilePlanWithReplacement(ctx context.Context, request Request, replacement *replacementContext) (binding.AdmittedTrialPlanV1, error) {
	input, err := prepareInputs(request)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	work := planCompilation{request: request, input: input, replacement: replacement, signatures: map[string]string{}, usedControls: map[string]bool{}}
	if err = work.prepareRows(ctx); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if err = work.createPlan(); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if err = work.compileEntries(ctx); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if err = work.retainMixedReferences(); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if err = validateDistinctSignatures(work.plan.Entries, work.signatures); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if err = work.retainControls(); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if err = compileAllocation(input.spec, &work.plan); err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	return work.seal()
}
func (w *planCompilation) prepareRows(ctx context.Context) error {
	var err error
	w.coordinates, err = coordinates(w.input.spec, w.request.Limits)
	if err != nil {
		return err
	}
	if err = validateMixedAssignments(w.request, w.input, w.coordinates, w.input.mixedProfiles); err != nil {
		return err
	}
	if len(w.request.RealizationAssignments) > 0 {
		w.input.mixed, err = prepareMixedAuthority(ctx, w.request, w.input, w.input.mixedProfiles)
		if err != nil {
			return err
		}
		w.input.refsJSON, err = canonicalMixedRefs(w.input.refsJSON)
		if err != nil {
			return err
		}
	}
	if err = w.prepareReplacementCoordinates(); err != nil {
		return err
	}
	w.rows, err = selectionRows(w.request, w.input.spec, w.coordinates, w.input.family.Points)
	return err
}
func (w *planCompilation) prepareReplacementCoordinates() error {
	var err error
	if w.replacement == nil {
		return nil
	}

	original := w.coordinates[w.replacement.index]
	w.coordinates, err = w.replacement.coordinates(w.coordinates)
	if err != nil {
		return err
	}
	if len(w.request.RealizationAssignments) > 0 {
		oldKey, keyErr := canonical(original.projection())
		if keyErr != nil {
			return keyErr
		}
		newKey, keyErr := canonical(w.coordinates[w.replacement.index].projection())
		if keyErr != nil {
			return keyErr
		}
		w.request.RealizationAssignments = maps.Clone(w.request.RealizationAssignments)
		w.request.RealizationAssignments[string(newKey)] = w.request.RealizationAssignments[string(oldKey)]
		delete(w.request.RealizationAssignments, string(oldKey))
	}

	return nil
}

type planIntent struct {
	Profiles    json.RawMessage            `json:"profiles"`
	Refs        json.RawMessage            `json:"input_refs"`
	Authority   json.RawMessage            `json:"execution_authority"`
	Coordinates []any                      `json:"coordinates"`
	Apparatus   json.RawMessage            `json:"apparatus,omitempty"`
	Assignments map[string]json.RawMessage `json:"realization_assignments,omitempty"`
}

func (w *planCompilation) intent() (planIntent, error) {
	profiles, err := compilerProfiles(w.input.spec, len(w.request.RealizationAssignments) > 0, w.replacement != nil)
	if err != nil {
		return planIntent{}, err
	}
	projections := make([]any, len(w.coordinates))
	for index, c := range w.coordinates {
		projections[index] = c.projection()
	}
	intent := planIntent{Profiles: profiles, Refs: w.input.refsJSON, Authority: w.input.authorityJSON, Coordinates: projections, Apparatus: w.input.apparatusJSON}
	if len(w.request.RealizationAssignments) == 0 {
		return intent, nil
	}
	intent.Apparatus = nil
	intent.Assignments = map[string]json.RawMessage{}
	for key, fragment := range w.request.RealizationAssignments {
		raw, _, err := mixedBinding(w.input.owner, fragment)
		if err != nil {
			return planIntent{}, err
		}
		intent.Assignments[key] = raw
	}
	return intent, nil
}
func (w *planCompilation) createPlan() error {
	intent, err := w.intent()
	if err != nil {
		return err
	}
	planID, err := identity("trial-plan", intent, len(w.request.RealizationAssignments) > 0)
	if err != nil {
		return err
	}
	if w.replacement != nil {
		planID, err = w.replacement.planID()
		if err != nil {
			return err
		}
	}
	w.plan = trialPlan{ID: planID, Profiles: intent.Profiles, Refs: w.input.refsJSON, Controls: map[string]json.RawMessage{}, Cleanup: map[string]json.RawMessage{}, Entries: map[string]trialEntry{}, ReplacementPolicy: w.input.spec.RunPlan.ReplacementPolicy, Parallelism: w.input.family.Parallelism}
	if isNull(w.plan.ReplacementPolicy) {
		w.plan.ReplacementPolicy = nil
	}
	if w.replacement != nil {
		w.plan.ReplacementOrigin, err = encoded(w.replacement.origin)
	}
	return err
}
func (w *planCompilation) compileEntries(ctx context.Context) error {
	failures := entryFailures{}
	retained := 0
	for index, c := range w.coordinates {
		if w.replacement != nil && index != w.replacement.index {
			continue
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		entry, cleanupID, cleanup, err := compileEntry(ctx, w.request, w.input, w.plan.ID, c, w.rows[index])
		if err != nil {
			if addErr := failures.add(err, c); addErr != nil {
				return addErr
			}
			continue
		}
		size, err := w.retainedBytes(entry, cleanup)
		if err != nil {
			return err
		}
		if retained += size; retained > w.request.Limits.MaxPlanBytes {
			// Retain no oversized aggregate, but preserve the canonical refusal order.
			clear(w.plan.Entries)
			clear(w.plan.Cleanup)
			clear(w.signatures)
			failures.refuse(&compilationRefusalError{"plan-byte-limit-exceeded", "", "canonical admitted plan bytes exceed the compilation limit"})
			continue
		}
		w.plan.Entries[entry.ID] = entry
		w.plan.Cleanup[cleanupID] = cleanup
		if entry.signature != "" {
			w.signatures[entry.ID] = entry.signature
		}
		if err = w.retainDrawControls(w.rows[index].draws); err != nil {
			return err
		}
	}
	return failures.result()
}
// retainedBytes charges one compiled entry and its cleanup plan at their sealed canonical size.
func (w *planCompilation) retainedBytes(entry trialEntry, cleanup json.RawMessage) (int, error) {
	raw, err := encoded(entry)
	if err != nil {
		return 0, err
	}
	return admission.TrialEntryRetainedBytes(w.input.owner, raw, cleanup)
}
func (w *planCompilation) retainDrawControls(draws []json.RawMessage) error {
	for _, raw := range draws {
		var draw drawRecord
		if decode(raw, &draw) != nil {
			return trialInvalid()
		}
		w.usedControls[draw.Control] = true
	}
	return nil
}
func (w *planCompilation) retainControls() error {
	for _, raw := range w.input.spec.RunPlan.Controls {
		var control stochasticControl
		if decode(raw, &control) != nil {
			return trialInvalid()
		}
		if w.usedControls[control.ID] {
			w.plan.Controls[control.ID] = raw
		}
	}
	return nil
}
func (w *planCompilation) seal() (binding.AdmittedTrialPlanV1, error) {
	w.plan.Admission.Stage = "admitted-sealed"
	w.plan.Admission.Count = len(w.plan.Entries)
	raw, err := encoded(w.plan)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	limits := ingress.Limits{MaxBytes: max(32<<20, w.request.Limits.MaxPlanBytes), MaxDepth: 64}
	sealed, err := admission.SealTrialPlan(w.input.owner, raw, limits)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	raw, err = admission.TrialPlanProjection(w.input.owner, sealed, limits)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if len(raw) > w.request.Limits.MaxPlanBytes {
		return binding.AdmittedTrialPlanV1{}, refuse("plan-byte-limit-exceeded", "", "canonical admitted plan bytes exceed the compilation limit")
	}
	var result binding.AdmittedTrialPlanV1
	err = decode(raw, &result)
	return result, err
}

func (w *planCompilation) retainMixedReferences() error {
	if w.replacement == nil || len(w.request.RealizationAssignments) == 0 {
		return nil
	}
	used := map[string]bool{}
	for _, entry := range w.plan.Entries {
		var assignment mixedAssignment
		if decode(entry.Apparatus, &assignment) != nil {
			return trialInvalid()
		}
		used[assignment.Profile.ID] = true
	}
	var refs map[string]json.RawMessage
	if decode(w.plan.Refs, &refs) != nil {
		return trialInvalid()
	}
	var profiles []json.RawMessage
	if decode(refs["mixed_composition_profile_refs"], &profiles) != nil {
		return trialInvalid()
	}
	filtered := []json.RawMessage{}
	for _, profile := range profiles {
		var ref reference
		if decode(profile, &ref) != nil {
			return trialInvalid()
		}
		if used[ref.ID] {
			filtered = append(filtered, profile)
		}
	}

	raw, err := encoded(filtered)
	if err != nil {
		return err
	}
	refs["mixed_composition_profile_refs"] = raw
	w.plan.Refs, err = encoded(refs)
	return err
}
