package admission

import (
	"encoding/json"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

type mixedStageFixture struct {
	TimeModel        json.RawMessage `json:"TimeModel"`
	TimeState        json.RawMessage `json:"TimeState"`
	PostTimeState    json.RawMessage `json:"PostTimeState"`
	CompositionState json.RawMessage `json:"CompositionState"`
	TimeModelRef     string          `json:"TimeModelRef"`
	TimeModelDigest  string          `json:"TimeModelDigest"`
}

type mixedStageTestContext struct {
	snapshot                     MixedBackendStageSnapshot
	request, binding             []byte
	responses, controls, reports [][]byte
}

func (c *mixedStageTestContext) OperationRequest() []byte                      { return c.request }
func (c *mixedStageTestContext) OperationResponses() [][]byte                  { return c.responses }
func (c *mixedStageTestContext) OperationControls() [][]byte                   { return c.controls }
func (c *mixedStageTestContext) MixedStageBinding() []byte                     { return c.binding }
func (c *mixedStageTestContext) MixedStageReports() [][]byte                   { return c.reports }
func (c *mixedStageTestContext) MixedStageSnapshot() MixedBackendStageSnapshot { return c.snapshot }

func mixedStageFixtureContext(t *testing.T, e *Validator, name string) *mixedStageTestContext {
	t.Helper()
	raw, err := os.ReadFile("testdata/mixed-stage-resolutions.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]mixedStageFixture
	if err = json.Unmarshal(raw, &fixtures); err != nil {
		t.Fatal(err)
	}
	g := fixtures[name]
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	model, err := e.Validate("time-model-v1", g.TimeModel, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	before, err := e.Validate("time-runtime-state-v1", g.TimeState, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	after, err := e.Validate("time-runtime-state-v1", g.PostTimeState, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	composition := []byte(g.CompositionState)
	if string(composition) == "null" {
		composition = nil
	}
	c := &mixedStageTestContext{snapshot: MixedBackendStageSnapshot{TimeModel: model, TimeState: before, PostTimeState: after, TimeModelRef: g.TimeModelRef, TimeModelDigest: g.TimeModelDigest, CompositionState: composition}}
	binding := "mixed-edge"
	if name == "mixed-handoff" || name == "mixed-handoff-stale" {
		binding = "mixed-handoff"
	}
	c.binding = controlJSON(t, fixtureObject(t, "fixtures/control-plane/mixed-backend-execution-binding-v1/valid/"+binding+".json"))
	c.request = controlJSON(t, fixtureObject(t, "fixtures/control-plane/backend-operation-request-v1/valid/"+name+".json"))
	c.responses = mixedStagePublishedRecords(t, "backend-operation-response-v1", name)
	c.reports = mixedStagePublishedRecords(t, "mixed-backend-stage-report-v1", name)
	return c
}

func mixedStagePublishedRecords(t *testing.T, id, name string) [][]byte {
	t.Helper()
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	paths, err := fs.Glob(source, "fixtures/control-plane/"+id+"/valid/"+name+"-0*.json")
	if err != nil {
		t.Fatal(err)
	}
	result := make([][]byte, 0, len(paths))
	for _, path := range paths {
		raw, err := fs.ReadFile(source, path)
		if err != nil {
			t.Fatal(err)
		}
		result = append(result, raw)
	}
	return result
}

func TestMixedStagesBindExactTimeOwnersAndTranscript(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	for _, name := range []string{"mixed-edge", "mixed-edge-partial", "mixed-edge-refused", "mixed-edge-time-refused", "mixed-handoff", "mixed-handoff-stale"} {
		t.Run(name, func(t *testing.T) {
			c := mixedStageFixtureContext(t, e, name)
			if len(c.reports) == 0 {
				mixedStageEmptyTranscript(t, e, c, limits)
				return
			}
			if _, err := e.Validate("mixed-backend-stage-report-v1", c.reports[len(c.reports)-1], limits, c); err != nil {
				t.Fatal(err)
			}
			c.snapshot.TimeModelDigest = "sha256:wrong"
			if _, err := e.Validate("mixed-backend-stage-report-v1", c.reports[0], limits, c); err == nil {
				t.Fatal("accepted another time-model resolution")
			}
		})
	}
}

func mixedStageEmptyTranscript(t *testing.T, e *Validator, c *mixedStageTestContext, limits ingress.Limits) {
	t.Helper()
	state, err := e.mixedStageInputs(c)
	if err != nil {
		t.Fatal(err)
	}
	if err = state.check(); err != nil {
		t.Fatal(err)
	}
	foreign := controlJSON(t, fixtureObject(t, "fixtures/control-plane/mixed-backend-stage-report-v1/valid/mixed-edge-01.json"))
	if _, err = e.Validate("mixed-backend-stage-report-v1", foreign, limits, c); err == nil {
		t.Fatal("accepted an unsupplied stage for refused invocation")
	}
}
