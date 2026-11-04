package admission

import (
	"encoding/json"
	"testing"
)

type testExperimentContext struct {
	testManifestContext

	task        []byte
	tasks, runs [][]byte
}

func (c testExperimentContext) ExperimentTask() []byte    { return c.task }
func (c testExperimentContext) ExperimentTasks() [][]byte { return c.tasks }
func (c testExperimentContext) ExperimentRuns() [][]byte  { return c.runs }
func (c testExperimentContext) AdmitSDLPhase(request SDLPhaseRequest) (SDLPhaseAdmission, error) {
	return (recordedSDLPhaseOwner{}).AdmitSDLPhase(request)
}
func TestTaskRunAndStudyJoins(t *testing.T) {
	e := boundTestOwner(t)
	task := fixtureObject(t, "fixtures/experiment-core/experiment-task-v1/valid/reference.json")
	run := fixtureObject(t, "fixtures/experiment-core/experiment-run-v1/valid/reference.json")
	raw, err := json.Marshal(task)
	if err != nil {
		t.Fatal(err)
	}
	c := testExperimentContext{testManifestContext: historicalManifestContext(t), task: raw, tasks: [][]byte{raw}}
	runRaw, err := json.Marshal(run)
	if err != nil {
		t.Fatal(err)
	}
	c.runs = [][]byte{runRaw}
	if err := validateTestDocument(t, e, "experiment-run-v1", run, c); err != nil {
		t.Fatal(err)
	}
	object(run["task_ref"])["ref_id"] = "foreign-task"
	if err := validateTestDocument(t, e, "experiment-run-v1", run, c); err == nil {
		t.Error("accepted foreign task")
	}
	study := fixtureObject(t, "fixtures/experiment-core/experiment-study-v1/valid/reference.json")
	if err := validateTestDocument(t, e, "experiment-study-v1", study, c); err != nil {
		t.Fatal(err)
	}
	c.runs = append(c.runs, runRaw)
	if err := validateTestDocument(t, e, "experiment-study-v1", study, c); err == nil {
		t.Error("accepted ambiguous evaluation membership")
	}
}

// These independently supplied historical manifests match the published run's
// pinned apparatus. Current installed manifest fixtures have newer identities.
func historicalManifestContext(t *testing.T) testManifestContext {
	t.Helper()
	processor := fixtureObject(t, "fixtures/processor-manifest/processor-manifest-v2/valid/reference.json")
	backend := fixtureObject(t, "fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	processor["identity"] = map[string]any{"name": "raes-reference-processor", "version": "0.1.0"}
	object(processor["compatibility"])["backends"] = []any{"stub-backend"}
	backend["identity"] = map[string]any{"name": "stub-backend", "version": "0.1.0"}
	object(backend["compatibility"])["processors"] = []any{"raes-reference-processor"}
	return testManifestContext{processor: controlJSON(t, processor), backend: controlJSON(t, backend)}
}
