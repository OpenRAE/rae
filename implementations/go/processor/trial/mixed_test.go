package trial

import (
	"context"
	"encoding/json"
	"errors"
	"maps"
	"os"
	"slices"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type mixedPair struct {
	Key   [2]string       `json:"key"`
	Value json.RawMessage `json:"value"`
}
type mixedContextReference struct {
	Scenarios   map[string]json.RawMessage `json:"scenario_snapshots"`
	Targets     map[string]string          `json:"compiled_targets"`
	Components  []mixedPair                `json:"components"`
	Allocations []mixedPair                `json:"allocations"`
	Edges       []mixedPair                `json:"edges"`
	Transitions []mixedPair                `json:"transitions"`
	TimeModels  map[string]json.RawMessage `json:"time_models"`
	TimeDigests map[string]string          `json:"time_model_digests"`
	Evidence    []mixedPair                `json:"evidence_satisfaction"`
	Nested      map[string]json.RawMessage `json:"nested_profiles"`
	Effects     []mixedPair                `json:"allocation_effects"`
	Resources   map[string][]string        `json:"resource_refs"`
	Membership  []mixedPair                `json:"projection_membership"`
}
type mixedCompilerContext struct {
	snapshot admission.MixedCompositionSnapshot
	refuse   bool
}

func (c *mixedCompilerContext) MixedCompositionSnapshot() admission.MixedCompositionSnapshot {
	return c.snapshot
}
func (c *mixedCompilerContext) ResolveMixedFeature(_, _ string, _ json.RawMessage) error {
	if c.refuse {
		return errors.New("private installed owner refusal")
	}
	return nil
}

type mixedCompilerReference struct {
	Name        string                           `json:"name"`
	Request     referenceRequest                 `json:"request"`
	Plan        json.RawMessage                  `json:"plan"`
	Assignments map[string]json.RawMessage       `json:"assignments"`
	Profiles    map[string]json.RawMessage       `json:"profiles"`
	Contexts    map[string]mixedContextReference `json:"contexts"`
	Envelopes   map[string]json.RawMessage       `json:"envelopes"`
}

func mixedCompilerReferences(t *testing.T) []mixedCompilerReference {
	t.Helper()
	raw, err := readCompressedReference("testdata/mixed-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []mixedCompilerReference `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid mixed reference")
	}
	if len(reference.Cases) != 4 {
		t.Fatal("mixed reference inventory changed")
	}
	return reference.Cases
}
func mixedCompilerRequest(t *testing.T, ref mixedCompilerReference) Request {
	t.Helper()
	request := compilerRequest(t, ref.Request)
	owner, err := trialOwner()
	if err != nil {
		t.Fatal(err)
	}
	request.MixedProfiles = map[string]validation.Value{}
	request.MixedProfileContexts = map[string]admission.MixedCompositionContext{}
	request.MixedRealizationEnvelopes = map[string]validation.Value{}
	request.RealizationAssignments = map[string]admission.Fragment{}
	for id, reference := range ref.Contexts {
		context := mixedContextFixture(t, owner, reference)
		request.MixedProfileContexts[id] = context
		value, err := owner.Validate("mixed-participant-composition-profile-v1", ref.Profiles[id], trialIngress(), context)
		if err != nil {
			t.Fatal("profile fixture refused", id, err)
		}
		request.MixedProfiles[id] = value
	}
	for key, raw := range ref.Assignments {
		var value any
		if decode(raw, &value) != nil {
			t.Fatal("invalid assignment")
		}
		fragment, err := admission.AdmitFragment(owner, admission.AdmittedMixedCompositionBinding, value, trialIngress())
		if err != nil {
			t.Fatal(err)
		}
		request.RealizationAssignments[key] = fragment
	}
	for id, raw := range ref.Envelopes {
		value, err := owner.Validate("realization-envelope-v1", raw, trialIngress(), nil)
		if err != nil {
			t.Fatal(err)
		}
		request.MixedRealizationEnvelopes[id] = value
	}
	return request
}
func rawByteMap(input map[string]json.RawMessage) map[string][]byte {
	result := map[string][]byte{}
	for k, v := range input {
		result[k] = v
	}
	return result
}
func mixedBytePairs(input []mixedPair) map[[2]string][]byte {
	result := map[[2]string][]byte{}
	for _, v := range input {
		result[v.Key] = v.Value
	}
	return result
}
func mixedStringPairs(t *testing.T, input []mixedPair) map[[2]string][]string {
	t.Helper()
	result := map[[2]string][]string{}
	for _, v := range input {
		var value []string
		if decode(v.Value, &value) != nil {
			t.Fatal("invalid context references")
		}
		result[v.Key] = value
	}
	return result
}
func TestMixedCompilerMatchesIndependentPlans(t *testing.T) {
	for _, ref := range mixedCompilerReferences(t) {
		t.Run(ref.Name, func(t *testing.T) {
			result, err := Compile(mixedCompilerRequest(t, ref))
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
			if !sameJSON(actual, ref.Plan) {
				var a, b any
				_ = json.Unmarshal(actual, &a)
				_ = json.Unmarshal(ref.Plan, &b)
				t.Fatal(cmp.Diff(b, a))
			}
		})
	}
}

func TestMixedCompilerRefusesUnresolvedAuthorityAndBoundedWork(t *testing.T) {
	raw, err := os.ReadFile("testdata/mixed-refusals.json")
	if err != nil {
		t.Fatal(err)
	}
	var ref struct {
		Cases []mixedRefusalCase `json:"cases"`
	}
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("invalid mixed refusals")
	}
	baseline := mixedCompilerReferences(t)[1]
	for _, test := range ref.Cases {
		t.Run(test.Name, func(t *testing.T) { checkMixedRefusal(t, test, baseline) })
	}
}

func TestMixedReplacementRetargetsAssignmentsAndReferences(t *testing.T) {
	raw, err := readCompressedReference("testdata/mixed-replacement-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			mixedCompilerReference

			Origin replacementOrigin `json:"origin"`
		} `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("fixture")
	}
	for _, item := range reference.Cases {
		t.Run(item.Name, func(t *testing.T) {
			request := mixedCompilerRequest(t, item.mixedCompilerReference)
			plan, compileErr := compilePlanWithReplacement(context.Background(), request, &replacementContext{origin: item.Origin, index: 0, maximum: 2})
			if compileErr != nil {
				t.Fatal(compileErr)
			}
			actual, _ := encoded(plan)
			if !sameJSON(actual, item.Plan) {
				t.Fatal("mixed replacement differs")
			}
			if _, compileErr = Compile(request); compileErr != nil {
				t.Fatal("original request was mutated", compileErr)
			}
		})
	}
}

type mixedRefusalCase struct {
	Name string `json:"name"`
	Code string `json:"code"`
}

func checkMixedRefusal(t *testing.T, test mixedRefusalCase, baseline mixedCompilerReference) {
	t.Helper()

	request := mixedCompilerRequest(t, baseline)
	ids := slices.Sorted(maps.Keys(request.MixedProfileContexts))
	context, ok := request.MixedProfileContexts[ids[0]].(*mixedCompilerContext)
	if !ok {
		t.Fatal("wrong fixture context")
	}
	switch test.Name {
	case "assignments":
		request.RealizationAssignments = nil
	case "profiles":
		request.MixedProfiles = nil
	case "context":
		request.MixedProfileContexts = nil
	case "envelopes":
		request.MixedRealizationEnvelopes = nil
	case "components":
		context.snapshot.Components = nil
	case "allocations":
		context.snapshot.Allocations = nil
	case "evidence":
		context.snapshot.EvidenceSatisfaction = nil
	case "time":
		context.snapshot.TimeModels = nil
	case "resources":
		context.snapshot.ResourceRefs = map[string][]string{ids[0]: {"range:unowned"}}
	case "projection":
		context.snapshot.ProjectionMembership = nil
	case "effects":
		context.snapshot.AllocationEffects = nil
	case "profile-limit":
		request.Limits.MaxMixedProfiles = 1
	case "work-limit":
		request.Limits.MaxMixedContextWork = 1
	case "component-limit":
		request.MixedCompositionLimits.MaxComponents = 1
	default:
		t.Fatal("unknown reference mutation")
	}
	result, err := Compile(request)
	if err != nil {
		t.Fatal(err)
	}
	if result.Plan != nil || len(result.Diagnostics) != 1 || result.Diagnostics[0].Code != test.Code {
		t.Fatal("authority refusal differs", result.Diagnostics, "want", test.Code)
	}
}

func mixedContextFixture(t *testing.T, owner *admission.Validator, reference mixedContextReference) *mixedCompilerContext {
	t.Helper()
	context := &mixedCompilerContext{snapshot: admission.MixedCompositionSnapshot{ScenarioSnapshots: rawByteMap(reference.Scenarios), CompiledTargets: reference.Targets, Components: mixedBytePairs(reference.Components), Allocations: mixedBytePairs(reference.Allocations), Edges: mixedBytePairs(reference.Edges), Transitions: mixedBytePairs(reference.Transitions), TimeModels: map[string]validation.Value{}, TimeModelDigests: reference.TimeDigests, EvidenceSatisfaction: mixedStringPairs(t, reference.Evidence), NestedProfiles: rawByteMap(reference.Nested), AllocationEffects: mixedStringPairs(t, reference.Effects), ResourceRefs: reference.Resources, ProjectionMembership: map[[2]string]bool{}}}
	for name, raw := range reference.TimeModels {
		value, err := owner.Validate("time-model-v1", raw, trialIngress(), nil)
		if err != nil {
			t.Fatal(err)
		}
		context.snapshot.TimeModels[name] = value
	}
	for _, member := range reference.Membership {
		var value bool
		if json.Unmarshal(member.Value, &value) != nil {
			t.Fatal("invalid membership")
		}
		context.snapshot.ProjectionMembership[member.Key] = value
	}
	return context
}
