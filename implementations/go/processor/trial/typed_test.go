package trial

import (
	"context"
	"encoding/json"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type typedReference struct {
	Cases      []referenceCompilation `json:"cases"`
	Treatments []struct {
		Name      string          `json:"name"`
		Treatment json.RawMessage `json:"treatment"`
		Valid     bool            `json:"valid"`
	} `json:"treatments"`
}

func typedReferences(t *testing.T) typedReference {
	t.Helper()
	raw, err := readCompressedReference("testdata/typed-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var reference typedReference
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid typed reference")
	}
	return reference
}
func TestTypedTreatmentUsesNativeFamilyAuthority(t *testing.T) {
	reference := typedReferences(t)
	request := compilerRequest(t, reference.Cases[0].Request)
	owner, err := trialOwner()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range reference.Treatments {
		t.Run(test.Name, func(t *testing.T) {
			var document any
			if decode(test.Treatment, &document) != nil {
				t.Fatal("invalid treatment")
			}
			fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, document, trialIngress())
			if err != nil {
				t.Fatal(err)
			}
			err = sdl.ValidateTreatment(request.Family, fragment)
			if (err == nil) != test.Valid {
				t.Fatal("treatment authority verdict", err, "want", test.Valid)
			}
		})
	}
}

// This installed owner fixture checks exact content pins and concrete scope.
// The production compiler must supply each selected scenario to the factory.
type typedContextFactory struct{}
type typedContextValidator struct {
	assets map[string]json.RawMessage
	roles  map[string]string
}

//nolint:ireturn // The installed factory contract returns the public validator interface.
func (typedContextFactory) ForScenario(_ context.Context, scenario sdl.Scenario) (admission.ParticipantControlContextValidator, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return nil, err
	}
	var model struct {
		Assets map[string]json.RawMessage `json:"control_context_assets"`
		Agents map[string]struct {
			Role string `json:"role"`
		} `json:"agents"`
	}
	if decode(raw, &model) != nil {
		return nil, trialInvalid()
	}
	roles := map[string]string{}
	for id, agent := range model.Agents {
		roles["agents."+id] = agent.Role
	}
	return typedContextValidator{model.Assets, roles}, nil
}
func (v typedContextValidator) ValidateControlContextReference(_ context.Context, participant string, selection admission.ControlContextSelection) error {
	raw := v.assets[strings.TrimPrefix(selection.DeclarationRef, "control_context_assets.")]
	var asset struct {
		ID           string   `json:"asset_id"`
		Version      string   `json:"asset_version"`
		Participants []string `json:"participant_addresses"`
		Roles        []string `json:"role_refs"`
	}
	if len(raw) == 0 || decode(raw, &asset) != nil {
		return trialInvalid()
	}
	digest, err := hash(raw)
	if err != nil {
		return err
	}
	role, exists := v.roles[participant]
	if !exists || selection.AssetRef.AssetID != asset.ID || selection.AssetRef.AssetVersion != asset.Version || selection.AssetRef.AssetDigest != digest || (!slices.Contains(asset.Participants, participant) && !slices.Contains(asset.Roles, role)) {
		return trialInvalid()
	}
	return nil
}
func typedCompilerRequest(t *testing.T, ref referenceCompilation) Request {
	t.Helper()
	request := compilerRequest(t, ref.Request)
	request.ParticipantControlContextFactories = map[ConfigurationValidatorKey]ControlContextFactory{{"participant-config", "1"}: typedContextFactory{}}
	return request
}
func TestTypedCompilerMatchesIndependentConfigurationsAndStructure(t *testing.T) {
	for _, reference := range typedReferences(t).Cases {
		t.Run(reference.Name, func(t *testing.T) {
			result, err := Compile(typedCompilerRequest(t, reference))
			if err != nil {
				t.Fatal(err)
			}
			if result.Plan == nil {
				t.Fatal(result.Diagnostics)
			}
			actual, err := encoded(result.Plan)
			if err != nil {
				t.Fatal(err)
			}
			if !sameJSON(actual, reference.Plan) {
				var a, b any
				_ = json.Unmarshal(actual, &a)
				_ = json.Unmarshal(reference.Plan, &b)
				t.Fatal(cmp.Diff(b, a))
			}
		})
	}
}

func TestTypedCompilerRefusesForgedTargetsAndEqualContent(t *testing.T) {
	raw, err := os.ReadFile("testdata/typed-refusals.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			Name    string           `json:"name"`
			Request referenceRequest `json:"request"`
			Code    string           `json:"code"`
		} `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid typed refusals")
	}
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) {
			request := typedCompilerRequest(t, referenceCompilation{Request: test.Request})
			result, err := Compile(request)
			if err != nil {
				t.Fatal(err)
			}
			if result.Plan != nil || len(result.Diagnostics) != 1 || result.Diagnostics[0].Code != test.Code {
				t.Fatal("typed refusal", result.Diagnostics, "want", test.Code)
			}
		})
	}
}

func TestTypedRealizationReplaysIndependentAuthoringSelections(t *testing.T) {
	raw, err := os.ReadFile("testdata/typed-replay-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var ref struct {
		Request referenceRequest `json:"request"`
		Plan    json.RawMessage  `json:"plan"`
		Entry   string           `json:"entry_id"`
		Digest  string           `json:"snapshot_digest"`
	}
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("invalid typed replay reference")
	}
	request := compilerRequest(t, ref.Request)
	owner, err := trialOwner()
	if err != nil {
		t.Fatal(err)
	}
	for _, change := range []string{"valid", "source", "fixed", "omit", "extra"} {
		t.Run(change, func(t *testing.T) { checkTypedReplay(t, change, request, ref.Plan, ref.Entry, ref.Digest, owner) })
	}
}

func checkTypedReplay(t *testing.T, change string, request Request, planRaw json.RawMessage, entryID, wantDigest string, owner *admission.Validator) {
	t.Helper()
	var err error

	var plan trialPlan
	if decode(planRaw, &plan) != nil {
		t.Fatal("bad source plan")
	}
	entry := plan.Entries[entryID]
	mutateReplaySelections(t, &entry, change)
	plan.Entries[entry.ID] = entry
	raw, err := encoded(plan)
	if err != nil {
		t.Fatal(err)
	}
	sealed, err := admission.SealTrialPlan(owner, raw, trialIngress())
	if err != nil {
		t.Fatal("resealed source fixture refused", change, err)
	}
	var carrier binding.AdmittedTrialPlanV1
	if decode(sealed.JSON(), &carrier) != nil {
		t.Fatal("bad generated plan")
	}
	inputs := RealizationInputs{Plan: carrier, Family: request.Family, Experiment: request.Experiment, Task: request.Task, CaptureSpecs: request.CaptureSpecs, ApparatusManifests: request.ApparatusManifests, ParticipantManifests: request.ParticipantManifests, RealizationEnvelope: request.RealizationEnvelope, BackendKey: ApparatusManifestKey{ComponentKind: componentBackend, ComponentName: "backend-a", ComponentVersion: "1", ManifestVersion: "backend-manifest/v2"}}
	result, err := RealizeEntry(inputs, entry.ID, RealizationOptions{})
	if change == "valid" {
		if err != nil || result.SnapshotDigest != wantDigest {
			t.Fatal("valid source replay", err, result.SnapshotDigest)
		}
	} else if err == nil {
		t.Fatal("resealed authoring mutation admitted", change)
	}
}

func mutateReplaySelections(t *testing.T, entry *trialEntry, change string) {
	t.Helper()
	for i := range entry.Selections {
		mutateReplaySelection(t, &entry.Selections[i], change)
	}
}
func mutateReplaySelection(t *testing.T, selection *selectionRecord, change string) {
	t.Helper()
	if isNull(selection.Treatment) {
		if change == "fixed" {
			selection.Outcome.Value = json.RawMessage(`"/opt/b"`)
		}
		return
	}
	var treatment map[string]any
	if decode(selection.Treatment, &treatment) != nil {
		t.Fatal("bad treatment")
	}
	switch change {
	case "source":
		treatment["source_factor_level_id"] = "other-source"
	case "omit":
		selection.Treatment = nil
		selection.Policy = "fixed-disguised"
		return
	case "extra":
		owner, ok := treatment["owner"].(map[string]any)
		if !ok {
			t.Fatal("bad owner")
		}
		owner["validator_version"] = "other-owner-version"
	}
	var err error
	selection.Treatment, err = encoded(treatment)
	if err != nil {
		t.Fatal(err)
	}
}
