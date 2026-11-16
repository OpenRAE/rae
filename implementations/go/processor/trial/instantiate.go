package trial

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type selectionProvenance struct {
	Point  string          `json:"variation_point_id"`
	Digest string          `json:"record_digest"`
	Record selectionRecord `json:"record"`
}
type bindingProvenance struct {
	ID     string          `json:"binding_id"`
	Digest string          `json:"record_digest"`
	Record json.RawMessage `json:"record"`
}
type instantiationProvenance struct {
	FamilyID     string                `json:"scenario_family_id"`
	FamilyDigest string                `json:"scenario_family_digest"`
	PlanID       string                `json:"plan_id"`
	PlanDigest   string                `json:"plan_digest"`
	EntryID      string                `json:"plan_entry_id"`
	EntryDigest  string                `json:"entry_digest"`
	RunID        string                `json:"run_id"`
	Coordinate   coordinate            `json:"coordinate"`
	Selections   []selectionProvenance `json:"selections"`
	Bindings     []bindingProvenance   `json:"bindings"`
}

// InstantiateEntry consumes recorded outcomes only after whole-plan admission.
//
//nolint:ireturn // The native SDL owner issues the opaque concrete scenario.
func InstantiateEntry(plan binding.AdmittedTrialPlanV1, entryID string, family sdl.Scenario) (sdl.InstantiatedScenario, error) {
	admitted, err := admitPlan(plan)
	if err != nil {
		return nil, err
	}
	owner, err := trialOwner()
	if err != nil {
		return nil, err
	}
	raw, err := admission.TrialPlanProjection(owner, admitted, trialIngress())
	if err != nil {
		return nil, err
	}
	var document trialPlan
	if decode(raw, &document) != nil {
		return nil, trialInvalid()
	}
	var refs inputReferences
	if decode(document.Refs, &refs) != nil {
		return nil, trialInvalid()
	}
	name, digest, err := instantiationFamily(refs.Family, family)
	if err != nil {
		return nil, err
	}
	entry, present := document.Entries[entryID]
	if !present {
		return nil, fault.New(fault.NotFound, "trial-entry-not-found", nil)
	}
	provenance := instantiationProvenance{FamilyID: name, FamilyDigest: digest, PlanID: document.ID, PlanDigest: document.Digest, EntryID: entry.ID, EntryDigest: entry.Digest, RunID: entry.RunID, Coordinate: entry.Coordinate, Selections: []selectionProvenance{}, Bindings: []bindingProvenance{}}
	outcomes, err := recordEntryProvenance(owner, family, entry, &provenance)
	if err != nil {
		return nil, err
	}
	selected, err := fragmentDocument(owner, outcomes)
	if err != nil {
		return nil, err
	}
	trial, err := fragmentDocument(owner, provenance)
	if err != nil {
		return nil, err
	}
	return sdl.Select(family, selected, trial)
}

func instantiationFamily(ref reference, family sdl.Scenario) (string, string, error) {
	digest, err := sdl.CanonicalDigest(family)
	if err != nil {
		return "", "", err
	}
	raw, err := sdl.DocumentBytes(family)
	if err != nil {
		return "", "", err
	}
	var metadata struct {
		Name string `json:"name"`
	}
	if decode(raw, &metadata) != nil {
		return "", "", trialInvalid()
	}
	if ref.ID != metadata.Name || text(ref.Digest) != digest {
		return "", "", trialInvalid()
	}
	return metadata.Name, digest, nil
}
func recordEntryProvenance(owner *admission.Validator, family sdl.Scenario, entry trialEntry, provenance *instantiationProvenance) (map[string]selectionOutcome, error) {
	outcomes := map[string]selectionOutcome{}
	for _, selection := range entry.Selections {
		if err := validateEntryTreatment(owner, family, selection); err != nil {
			return nil, err
		}
		d, checkErr := hash(selection)
		if checkErr != nil {
			return nil, checkErr
		}
		provenance.Selections = append(provenance.Selections, selectionProvenance{selection.Point, d, selection})
		outcomes[selection.Point] = selection.Outcome
	}
	for _, raw := range entry.Bindings {
		var b struct {
			Descriptor descriptor `json:"descriptor"`
		}
		if decode(raw, &b) != nil {
			return nil, trialInvalid()
		}
		d, checkErr := hash(raw)
		if checkErr != nil {
			return nil, checkErr
		}
		provenance.Bindings = append(provenance.Bindings, bindingProvenance{b.Descriptor.ID, d, raw})
	}
	return outcomes, nil
}

func validateEntryTreatment(owner *admission.Validator, family sdl.Scenario, selection selectionRecord) error {
	if !isNull(selection.Treatment) {
		fragment, checkErr := fragmentDocument(owner, selection.Treatment)
		if checkErr != nil {
			return checkErr
		}
		if checkErr = sdl.ValidateTreatment(family, fragment); checkErr != nil {
			return checkErr
		}
	}
	return nil
}
