package admission

import (
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type fullReferenceOwners struct {
	Processor        json.RawMessage            `json:"processor"`
	Backend          json.RawMessage            `json:"backend"`
	Task             json.RawMessage            `json:"task"`
	Runs             map[string]json.RawMessage `json:"runs"`
	Taxonomy         json.RawMessage            `json:"taxonomy"`
	Scenario         json.RawMessage            `json:"scenario"`
	ScenarioDigest   string                     `json:"scenario_digest"`
	Declarations     []ControlDeclaration       `json:"control_declarations"`
	ControlV1        []json.RawMessage          `json:"control_v1"`
	ControlV2        []json.RawMessage          `json:"control_v2"`
	Policies         []json.RawMessage          `json:"control_policies"`
	Crossing         []json.RawMessage          `json:"crossing"`
	Subjects         []json.RawMessage          `json:"crossing_subjects"`
	CrossingPolicies []json.RawMessage          `json:"crossing_policies"`
	Evidence         []string                   `json:"crossing_evidence"`
	Authorities      []string                   `json:"crossing_authorities"`
	Claims           map[string]json.RawMessage `json:"claims"`
	BackendOperation map[string]json.RawMessage `json:"backend_operation"`
	Inject           map[string]json.RawMessage `json:"inject"`
	Cleanup          json.RawMessage            `json:"cleanup"`
}

func loadFullReferenceOwners(t *testing.T) fullReferenceOwners {
	t.Helper()
	var owners fullReferenceOwners
	readFullReferenceJSON(t, "testdata/full-admission-owners.json", &owners)
	return owners
}
func fullReferenceContext(t *testing.T, e *Validator, o fullReferenceOwners, key string) any {
	t.Helper()
	switch key {
	case "sdl-phase":
		return recordedSDLPhaseOwner{}
	case "none":
		return nil
	case "backend-operation":
		return testBackendContext{request: o.BackendOperation["request"], control: o.BackendOperation["control"], admission: o.BackendOperation["admission"], installed: o.BackendOperation["installed"]}
	case "cleanup":
		return testCleanupContext{data: o.Cleanup}
	case "experiment", "experiment-typed":
		return fullExperimentOwner(o, key)
	case "taxonomy":
		return testCompletenessContext{taxonomy: o.Taxonomy}
	case "control-v1":
		return controlHistoryTestContext{records: fullReferenceBytes(o.ControlV1), declarations: o.Declarations}
	case "control-v2":
		return controlHistoryTestContext{records: fullReferenceBytes(o.ControlV2), policies: fullReferenceBytes(o.Policies)}
	case "crossing":
		return fullCrossingOwner{o}
	case "archive":
		_, context := materializationArchiveTestFixture(t)
		return context
	case "execution":
		var cases []materializationExecutionFixture
		readFullReferenceJSON(t, "testdata/materialization-execution.json", &cases)
		return materializationExecutionTestFixture(t, e, cases[0])
	case "inventory":
		return materializationInventoryTestFixture(t, e, materializationInventoryCases(t)[0])
	}
	if name, ok := strings.CutPrefix(key, "inject:"); ok {
		return fullInjectOwner(t, o, name)
	}
	if name, ok := strings.CutPrefix(key, "mixed-binding:"); ok {
		_, owner := mixedBackendFixture(t, e, name)
		return owner
	}
	if name, ok := strings.CutPrefix(key, "mixed-stage:"); ok {
		return mixedStageFixtureContext(t, e, name)
	}
	if name, ok := strings.CutPrefix(key, "claim:"); ok {
		claim, present := o.Claims[name]
		if !present {
			t.Fatal("missing independent claim")
		}
		return testBehavioralContext{claim: claim}
	}
	if name, ok := strings.CutPrefix(key, "associated:"); ok {
		return fullAssociatedOwner(t, e, o, name)
	}
	t.Fatal("unknown full reference owner:", key)
	return nil
}
func fullExperimentOwner(o fullReferenceOwners, key string) testExperimentContext {
	name := "reference"
	if key == "experiment-typed" {
		name = "typed-treatment"
	}
	return testExperimentContext{processor: o.Processor, backend: o.Backend, task: o.Task, tasks: [][]byte{o.Task}, runs: [][]byte{o.Runs[name]}}
}
func fullAssociatedOwner(t *testing.T, e *Validator, o fullReferenceOwners, name string) associatedFixtureContext {
	t.Helper()
	parentID := "sdl-authoring-input-v1"
	raw := o.Scenario
	switch name {
	case "task":
		parentID = "experiment-task-v1"
		raw = o.Task
	case "run":
		parentID = "experiment-run-v1"
		raw = o.Runs["reference"]
	case "authoring-input", "apparatus-context", "study":
		parentID = map[string]string{"authoring-input": "experiment-authoring-input-v1", "apparatus-context": "experiment-apparatus-context-v1", "study": "experiment-study-v1"}[name]
		raw = controlJSON(t, fixtureObject(t, "fixtures/experiment-core/"+parentID+"/valid/reference.json"))
	}
	parent, err := e.Validate(parentID, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, fullExperimentOwner(o, "experiment"))
	if err != nil {
		t.Fatal("independent parent:", err)
	}
	return associatedFixtureContext{parent: parent, payloads: map[string]io.Reader{"operator-guide": strings.NewReader("operator guide\n")}, snapshotDigest: o.ScenarioDigest}
}
func fullReferenceBytes(rows []json.RawMessage) [][]byte {
	result := make([][]byte, len(rows))
	for i, row := range rows {
		result[i] = row
	}
	return result
}

type fullCrossingOwner struct{ fullReferenceOwners }

func (c fullCrossingOwner) CrossingOccurrences() [][]byte { return fullReferenceBytes(c.Crossing) }
func (c fullCrossingOwner) CrossingSubjects() [][]byte    { return fullReferenceBytes(c.Subjects) }
func (c fullCrossingOwner) CrossingPolicies() [][]byte {
	return fullReferenceBytes(c.fullReferenceOwners.CrossingPolicies)
}
func (c fullCrossingOwner) CrossingEvidenceRefs() []string  { return c.Evidence }
func (c fullCrossingOwner) CrossingAuthorityRefs() []string { return c.Authorities }

func fullInjectOwner(t *testing.T, o fullReferenceOwners, name string) testInjectContext {
	t.Helper()
	occurrence := o.Inject["occurrence"]
	if name == "retry" {
		occurrence = o.Inject["retry"]
	}
	actor := stringAt(decodeRuleObject(t, string(occurrence)), "admission", "actor_id")
	return testInjectContext{occurrence: occurrence, request: o.Inject["request"], outcome: o.Inject["outcome"], claims: [][]byte{occurrence}, actor: actor}
}
