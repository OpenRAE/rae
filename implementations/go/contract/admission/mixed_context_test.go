package admission

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type mixedReferenceFixture struct {
	Profile         json.RawMessage            `json:"Profile"`
	Scenario        json.RawMessage            `json:"Scenario"`
	TimeModel       json.RawMessage            `json:"TimeModel"`
	TimeDigest      string                     `json:"TimeDigest"`
	CompiledTargets map[string]string          `json:"CompiledTargets"`
	Evidence        map[string][]string        `json:"Evidence"`
	Components      map[string]json.RawMessage `json:"Components"`
	Allocations     map[string]json.RawMessage `json:"Allocations"`
	Edges           map[string]json.RawMessage `json:"Edges"`
	Transitions     map[string]json.RawMessage `json:"Transitions"`
	Features        map[string]json.RawMessage `json:"Features"`
}

type mixedTestContext struct {
	snapshot MixedCompositionSnapshot
	features map[string]json.RawMessage
	refuse   bool
}

func (c *mixedTestContext) MixedCompositionSnapshot() MixedCompositionSnapshot { return c.snapshot }
func (c *mixedTestContext) ResolveMixedFeature(_, component string, raw json.RawMessage) error {
	parsed, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return err
	}
	trusted := c.features[component+"/"+stringAt(parsed, "feature")]
	if c.refuse || len(trusted) == 0 {
		return errors.New("private-feature-owner")
	}
	declared, err := ingress.Parse(trusted, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return err
	}
	return require(equal(parsed, declared))
}

func mixedRawIndex(profile string, raw map[string]json.RawMessage) map[[2]string][]byte {
	result := map[[2]string][]byte{}
	for key, data := range raw {
		result[[2]string{profile, key}] = data
	}
	return result
}

func mixedContextFixture(t *testing.T, e *Validator, name string) ([]byte, *mixedTestContext) {
	t.Helper()
	// Python's _context owner fixture admitted all three profiles independently.
	raw, err := os.ReadFile("testdata/mixed-composition-resolution.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]mixedReferenceFixture
	if err = json.Unmarshal(raw, &fixtures); err != nil {
		t.Fatal(err)
	}
	g := fixtures[name]
	v, err := ingress.Parse(g.Profile, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		t.Fatal(err)
	}
	id := stringAt(v, "profile_id")
	model, err := e.Validate("time-model-v1", g.TimeModel, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	evidence := map[[2]string][]string{}
	for obligation, refs := range g.Evidence {
		evidence[[2]string{id, obligation}] = refs
	}
	s := MixedCompositionSnapshot{ScenarioSnapshots: map[string][]byte{stringAt(v, "scenario_snapshot_ref", "ref_id"): g.Scenario}, CompiledTargets: g.CompiledTargets, Components: mixedRawIndex(id, g.Components), Allocations: mixedRawIndex(id, g.Allocations), Edges: mixedRawIndex(id, g.Edges), Transitions: mixedRawIndex(id, g.Transitions), TimeModels: map[string]validation.Value{"time-model:composition": model}, TimeModelDigests: map[string]string{"time-model:composition": g.TimeDigest}, EvidenceSatisfaction: evidence}
	return g.Profile, &mixedTestContext{snapshot: s, features: g.Features}
}

func TestMixedCompositionResolvesIndependentAuthorityAndTime(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	for _, name := range []string{"simultaneous", "alternative", "staged"} {
		t.Run(name, func(t *testing.T) {
			raw, c := mixedContextFixture(t, e, name)
			if _, err := e.Validate("mixed-participant-composition-profile-v1", raw, limits, c); err != nil {
				t.Fatal(err)
			}
		})
	}
	for _, name := range []string{"scenario", "target", "component", "allocation", "edge", "time", "evidence", "feature"} {
		t.Run(name, func(t *testing.T) {
			raw, c := mixedContextFixture(t, e, "simultaneous")
			mixedContextMutation(c, name)
			if _, err := e.Validate("mixed-participant-composition-profile-v1", raw, limits, c); err == nil {
				t.Fatal("accepted unresolved composition authority")
			}
		})
	}
}

func mixedContextMutation(c *mixedTestContext, name string) {
	switch name {
	case "scenario":
		c.snapshot.ScenarioSnapshots = nil
	case "target":
		c.snapshot.CompiledTargets = nil
	case "component":
		c.snapshot.Components = nil
	case "allocation":
		c.snapshot.Allocations = nil
	case "edge":
		c.snapshot.Edges = nil
	case "time":
		c.snapshot.TimeModelDigests = nil
	case "evidence":
		c.snapshot.EvidenceSatisfaction = nil
	case "feature":
		c.refuse = true
	}
}
