package trial

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func factorialRows(request Request, spec experimentSpec, coordinates []coordinate, points map[string]json.RawMessage) ([]selectionRow, error) {
	var design struct {
		Profile string `json:"profile"`
	}
	if decode(spec.Factorial, &design) != nil {
		return nil, trialInvalid()
	}
	if design.Profile == "factorial-bindings-v1" && len(spec.RunPlan.Policies) > 0 {
		return nil, refuse("factorial-selection-conflict", pathSelectionPolicies, "factorial binding selection cannot also declare selection policies")
	}
	var descriptors struct {
		Descriptors []descriptor `json:"descriptors"`
	}
	if !isNull(spec.Bindings) && decode(spec.Bindings, &descriptors) != nil {
		return nil, trialInvalid()
	}
	rows := make([]selectionRow, len(coordinates))
	for index, c := range coordinates {
		row, err := factorialRow(request, spec, c, descriptors.Descriptors, design.Profile, points)
		if err != nil {
			return nil, err
		}
		rows[index] = row
	}
	return rows, nil
}
func factorialRow(request Request, spec experimentSpec, c coordinate, descriptors []descriptor, profile string, points map[string]json.RawMessage) (selectionRow, error) {
	selections, err := factorialScalarSelections(c, descriptors, profile)
	if err != nil {
		return selectionRow{}, err
	}
	if profile == profileFactorialTreatments {
		typed, typedErr := factorialTypedSelections(request, spec, c)
		if typedErr != nil {
			return selectionRow{}, typedErr
		}
		selections = append(selections, typed...)
		for _, policy := range spec.RunPlan.Policies {
			selections = append(selections, policySelection(policy, policy.Outcome))
		}
	}
	merged, err := mergeSelections(nil, selections)
	if err != nil {
		return selectionRow{}, err
	}
	if len(merged) != len(points) {
		return selectionRow{}, refuse("variation-points-uncovered", pathFactorialDesign, "factorial bindings must cover every scenario variation point exactly once")
	}
	for _, selection := range merged {
		if _, present := points[selection.Point]; !present {
			return selectionRow{}, trialInvalid()
		}
	}
	return selectionRow{selections: merged, draws: []json.RawMessage{}}, nil
}
func factorialScalarSelections(c coordinate, descriptors []descriptor, profile string) ([]selectionRecord, error) {
	selections := []selectionRecord{}
	for _, d := range descriptors {
		if d.Condition != text(c.ConditionID) || d.Target.Plane != "scenario" {
			continue
		}
		if d.Value.Kind != "literal" {
			return nil, refuse("factorial-scenario-value-unsupported", pathFactorialDesign, "factorial scenario bindings require literal scalar outcomes")
		}
		selections = append(selections, selectionRecord{Point: d.Target.Point, Policy: profile, Kind: policyStratified, Outcome: d.Value})
	}
	return selections, nil
}
func factorialTypedSelections(request Request, spec experimentSpec, c coordinate) ([]selectionRecord, error) {
	var assignment struct {
		Selections []json.RawMessage `json:"required_selections"`
	}
	if spec.RunPlan.Allocation == nil || decode(spec.RunPlan.Allocation.Assignments[text(c.ConditionID)], &assignment) != nil {
		return nil, trialInvalid()
	}
	rows := make([]selectionRecord, len(assignment.Selections))
	for index, raw := range assignment.Selections {
		selection, err := factorialTreatment(request, raw)
		if err != nil {
			return nil, err
		}
		rows[index] = selection
	}
	return rows, nil
}
func factorialTreatment(request Request, raw json.RawMessage) (selectionRecord, error) {
	owner, err := trialOwner()
	if err != nil {
		return selectionRecord{}, err
	}
	fragment, err := fragmentDocument(owner, raw)
	if err != nil {
		return selectionRecord{}, err
	}
	if sdl.ValidateTreatment(request.Family, fragment) != nil {
		return selectionRecord{}, refuse("selection-treatment-rejected", pathFactorialDesign, "a typed selection failed authoritative scenario-family admission")
	}
	var treatment struct {
		Target  descriptorTarget `json:"target"`
		Outcome selectionOutcome `json:"outcome"`
	}
	if decode(raw, &treatment) != nil {
		return selectionRecord{}, trialInvalid()
	}
	return selectionRecord{Point: treatment.Target.Point, Policy: profileFactorialTreatments, Kind: policyStratified, Outcome: treatment.Outcome, Treatment: raw}, nil
}
func factorialEntryBindings(request Request, input compilationInputs, c coordinate, row selectionRow) ([]json.RawMessage, []admittedDescriptor, error) {
	result := []json.RawMessage{}
	selected := []admittedDescriptor{}
	for _, item := range input.descriptors {
		if item.wire.Condition != text(c.ConditionID) {
			continue
		}
		if err := factorialBindingSelection(request, item.wire, row); err != nil {
			return nil, nil, err
		}

		raw, err := encoded(struct {
			Descriptor json.RawMessage `json:"descriptor"`
			Origin     string          `json:"origin"`
		}{item.raw, originSelection})
		if err != nil {
			return nil, nil, err
		}
		result = append(result, raw)
		selected = append(selected, item)
	}
	work := len(result)
	for _, selection := range row.selections {
		if !isNull(selection.Treatment) || selection.Kind == policyFixed {
			work += 1 + len(selection.Outcome.MemberIDs)
		}
	}
	if work > request.Limits.MaxBindingsPerEntry {
		return nil, nil, refuse("binding-limit-exceeded", pathBindingDescriptors, "entry bindings exceed the compilation limit")
	}
	return result, selected, nil
}
func factorialBindingSelection(request Request, d descriptor, row selectionRow) error {
	if d.Target.Plane != "scenario" {
		return nil
	}
	for _, selection := range row.selections {
		if descriptorMatches(request, d, selection) {
			return nil
		}
	}
	return refuse("binding-selection-mismatch", pathBindingDescriptors, "factorial binding differs from the selected scenario outcome")
}

func factorialSignature(entry trialEntry, scenario sdl.InstantiatedScenario, typed bool) (string, error) {
	if typed {
		return typedFactorialSignature(entry, scenario)
	}
	operational, err := bindingEffects(entry.Bindings, true)
	if err != nil {
		return "", err
	}
	participants, err := scalarParticipantEffects(entry.Configurations)
	if err != nil {
		return "", err
	}
	return hash([]any{operational, participants})
}

func validateDistinctSignatures(entries map[string]trialEntry, signatures map[string]string) error {
	conditions := map[string]string{}
	for id, signature := range signatures {
		condition := text(entries[id].Coordinate.ConditionID)
		if prior, present := conditions[signature]; present && prior != condition {
			return refuse("factorial-conditions-indistinguishable", pathFactorialDesign, "distinct factorial conditions must remain operationally distinguishable after owner resolution")
		}
		conditions[signature] = condition
	}
	return nil
}

func factorialDefaultConfigurations(input compilationInputs) map[ParticipantManifestKey][]admission.ConfigurationOverride {
	grouped := map[ParticipantManifestKey][]admission.ConfigurationOverride{}
	if isNull(input.spec.Factorial) {
		return grouped
	}
	for _, item := range input.descriptors {
		t := item.wire.Target
		if t.Plane != planeParticipant {
			continue
		}
		key := ParticipantManifestKey{ParticipantAddress: t.Participant, ImplementationName: t.Name, ImplementationVersion: t.Version, ManifestVersion: t.ManifestVersion}
		if _, selected := input.participants[key]; selected {
			grouped[key] = []admission.ConfigurationOverride{}
		}
	}
	return grouped
}
