package trial

import (
	"context"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type entryCompilation struct {
	request    Request
	input      compilationInputs
	planID     string
	coordinate coordinate
	row        selectionRow
	assignment *mixedAssignment
	selected   sdl.InstantiatedScenario
	entry      trialEntry
	cleanupID  string
	cleanup    json.RawMessage
	template   cleanupTemplate
}

func compileEntry(ctx context.Context, request Request, input compilationInputs, planID string, c coordinate, row selectionRow) (trialEntry, string, json.RawMessage, error) {
	work := entryCompilation{request: request, input: input, planID: planID, coordinate: c, row: row}
	if err := work.selectAuthority(); err != nil {
		return trialEntry{}, "", nil, err
	}
	work.entry = trialEntry{Coordinate: c, Selections: row.selections, Draws: row.draws, Bindings: []json.RawMessage{}, Apparatus: work.input.apparatusJSON}
	if err := work.selectScenario(); err != nil {
		return work.entry, "", nil, err
	}
	if err := work.admitSupport(); err != nil {
		return work.entry, "", nil, err
	}
	if err := work.deriveIdentities(); err != nil {
		return work.entry, "", nil, err
	}
	if err := work.configure(ctx); err != nil {
		return work.entry, "", nil, err
	}
	if err := work.admitControls(); err != nil {
		return work.entry, "", nil, err
	}
	// Each entry retains the safe-state proof of its own selected scenario.
	safeStates, err := sdl.SafeStates(work.selected)
	if err != nil {
		return work.entry, "", nil, err
	}
	work.entry.SafeStates = safeStates
	return work.entry, work.cleanupID, work.cleanup, nil
}
func (w *entryCompilation) selectAuthority() error {
	if len(w.request.RealizationAssignments) == 0 {
		return nil
	}
	key, err := canonical(w.coordinate.projection())
	if err != nil {
		return err
	}
	raw, binding, err := mixedBinding(w.input.owner, w.request.RealizationAssignments[string(key)])
	if err != nil {
		return err
	}
	w.assignment = &binding
	authority := w.input.mixed[binding.Profile.ID]
	w.input.backends = authority.backends
	w.input.manifests = authority.manifests
	w.input.apparatusJSON = raw
	w.input.descriptors, err = admittedDescriptors(w.request, w.input)
	return err
}
func (w *entryCompilation) selectScenario() error {
	outcomes := map[string]selectionOutcome{}
	for _, selection := range w.row.selections {
		outcomes[selection.Point] = selection.Outcome
	}
	fragment, err := fragmentDocument(w.input.owner, outcomes)
	if err != nil {
		return err
	}
	w.selected, err = sdl.Select(w.request.Family, fragment, nil)
	if err != nil {
		return refuse("selected-scenario-rejected", "/entries/"+text(w.coordinate.ReplicateID), "the complete selection failed SDL-owned whole-scenario admission")
	}
	if w.assignment != nil {
		return validateMixedSelected(w.request, w.input, *w.assignment, w.selected)
	}
	diagnostics, err := sdl.EnvelopeMembershipDiagnostics(w.selected, w.input.envelope)
	if err != nil {
		return err
	}
	if len(diagnostics) > 0 {
		return refuse("realization-envelope-membership-rejected", "/entries/"+text(w.coordinate.ReplicateID), "the selected scenario is outside the admitted realization envelope")
	}
	return nil
}
func (w *entryCompilation) deriveIdentities() error {
	projection := struct {
		Plan        string          `json:"plan_id"`
		Coordinate  any             `json:"coordinate"`
		Realization json.RawMessage `json:"realization,omitempty"`
	}{Plan: w.planID, Coordinate: w.coordinate.projection()}
	if w.assignment != nil {
		projection.Realization = w.entry.Apparatus
	}
	var err error
	w.entry.ID, err = identity("trial-entry", projection, w.assignment != nil)
	if err != nil {
		return err
	}
	w.entry.RunID, err = identity("archival-run", projection, w.assignment != nil)
	if err != nil {
		return err
	}
	w.cleanupID, err = identity("trial-cleanup", struct {
		Entry    string          `json:"plan_entry_id"`
		Run      string          `json:"run_id"`
		Template json.RawMessage `json:"template"`
	}{w.entry.ID, w.entry.RunID, w.input.authority.Cleanup}, false)
	if err != nil {
		return err
	}
	if decode(w.input.authority.Cleanup, &w.template) != nil {
		return trialInvalid()
	}
	w.cleanup, err = encoded(boundCleanup{w.template, "trial-cleanup-plan/v1", w.cleanupID, w.entry.ID, w.entry.RunID})
	if err != nil {
		return err
	}
	w.entry.Controls = executionControls{w.input.authority.Timeout, w.input.authority.OnTimeout, w.input.authority.OnCancellation, w.cleanupID}
	w.entry.Provenance = entryProvenance{w.planID, w.entry.ID, w.entry.RunID, w.input.family.Name}
	return nil
}
func (w *entryCompilation) configure(ctx context.Context) error {
	bindings, selected, err := entryBindings(w.request, w.input, w.coordinate, w.row)
	if err != nil {
		return err
	}
	if len(w.row.draws) > w.request.Limits.MaxDrawsPerEntry {
		return refuse("draw-limit-exceeded", "/run_plan/stochastic_controls", "entry random draws exceed the compilation limit")
	}
	w.entry.Bindings = bindings
	w.entry.Configurations, err = entryConfigurations(ctx, w.request, w.input, w.selected, selected)
	if err != nil {
		return err
	}
	w.entry.signature, err = entryFactorialSignature(w.entry, w.input.spec, w.selected)
	if err != nil {
		return err
	}

	return nil
}
func entryFactorialSignature(entry trialEntry, spec experimentSpec, selected sdl.InstantiatedScenario) (string, error) {
	if isNull(spec.Factorial) {
		return "", nil
	}
	var design struct {
		Profile string `json:"profile"`
	}
	if decode(spec.Factorial, &design) != nil {
		return "", trialInvalid()
	}
	return factorialSignature(entry, selected, design.Profile == profileFactorialTreatments)
}
func (w *entryCompilation) admitSupport() error {
	keys := slices.SortedFunc(maps.Keys(w.input.backends), func(a, b ApparatusManifestKey) int {
		if a.ComponentName < b.ComponentName {
			return -1
		}
		if a.ComponentName > b.ComponentName {
			return 1
		}
		return 0
	})
	for _, key := range keys {
		input := w.input
		if w.assignment != nil {
			input.envelope = w.input.mixed[w.assignment.Profile.ID].envelopes[key]
		}
		if err := admitEntrySupport(w.request, input, w.selected, w.input.backends[key]); err != nil {
			return err
		}
	}
	return nil
}

func (w *entryCompilation) admitControls() error {
	for _, backend := range w.input.backends {
		if err := admitTrialControls(backend, w.entry.Controls, w.template); err != nil {
			return err
		}
	}
	return nil
}
