package admission

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type materializationPhaseFixture struct {
	SourceSHA256             string                         `json:"SourceSHA256"`
	Document                 json.RawMessage                `json:"Document"`
	FullDocument             json.RawMessage                `json:"FullDocument"`
	Resources                []json.RawMessage              `json:"Resources"`
	RealizationRequirements  []json.RawMessage              `json:"RealizationRequirements"`
	CollectionIdentities     map[string][]string            `json:"CollectionIdentities"`
	NodeCollection           json.RawMessage                `json:"NodeCollection"`
	NodeConcerns             map[string][]json.RawMessage   `json:"NodeConcerns"`
	PreparedNodeRequirements map[string][]json.RawMessage   `json:"PreparedNodeRequirements"`
	OrdinarySelections       map[string]string              `json:"OrdinarySelections"`
	NodePresence             map[string]map[string][]string `json:"NodePresence"`
}

func (p materializationPhaseFixture) compilation() MaterializationCompilation {
	resources := make([][]byte, len(p.Resources))
	for index, raw := range p.Resources {
		resources[index] = raw
	}
	requirements := make([][]byte, len(p.RealizationRequirements))
	for index, raw := range p.RealizationRequirements {
		requirements[index] = raw
	}
	return MaterializationCompilation{SourceSHA256: p.SourceSHA256, Document: p.Document, FullDocument: p.FullDocument, Resources: resources, RealizationRequirements: requirements, CollectionIdentities: p.CollectionIdentities, NodeCollection: materializationOptionalFixture(p.NodeCollection), NodeConcerns: materializationFixtureRows(p.NodeConcerns), PreparedNodeRequirements: materializationFixtureRows(p.PreparedNodeRequirements), OrdinarySelections: p.OrdinarySelections, NodePresence: p.NodePresence}
}

type materializationExecutionFixture struct {
	Name        string                      `json:"Name"`
	Submission  string                      `json:"Submission"`
	Plan        json.RawMessage             `json:"Plan"`
	Manifest    json.RawMessage             `json:"Manifest"`
	Predecessor json.RawMessage             `json:"Predecessor"`
	Actual      json.RawMessage             `json:"Actual"`
	Original    materializationPhaseFixture `json:"Original"`
	Current     materializationPhaseFixture `json:"Current"`
}

type materializationExecutionTestContext struct {
	snapshot          MaterializationExecutionSnapshot
	original, current MaterializationCompilation
}

func (c *materializationExecutionTestContext) MaterializationExecutionSnapshot() MaterializationExecutionSnapshot {
	return c.snapshot
}
func (c *materializationExecutionTestContext) CompileMaterialization(request MaterializationCompileRequest) (MaterializationCompilation, error) {
	if request.Plan.ContractID() != "provisioning-plan-v1" {
		return MaterializationCompilation{}, errors.New("wrong compiler plan")
	}
	phase := c.current
	if request.ContractID == "instantiated-scenario-v1" {
		phase = c.original
	}
	if digest.SHA256(request.Source) != phase.SourceSHA256 {
		return MaterializationCompilation{}, errors.New("wrong compiler source")
	}
	return phase, nil
}
func (c *materializationExecutionTestContext) NormalizeMaterializationNode(request MaterializationNodeProjection) (json.RawMessage, error) {
	// Both operands must belong to independent compiler/resource outputs. Return
	// the recorded typed Node; never derive trusted data from the candidate.
	var operand any
	if err := json.Unmarshal(request.Node, &operand); err != nil {
		return nil, err
	}
	for _, phase := range []MaterializationCompilation{c.original, c.current} {
		var full map[string]any
		if err := json.Unmarshal(phase.FullDocument, &full); err != nil {
			return nil, err
		}
		for _, resource := range phase.Resources {
			var row any
			if err := json.Unmarshal(resource, &row); err != nil {
				return nil, err
			}
			if stringAt(row, "payload", "name") == request.Name && equal(at(row, "payload", "spec", "node"), operand) {
				return json.Marshal(at(full, "nodes", request.Name))
			}
		}
	}
	return nil, errors.New("unknown normalized node")
}

func materializationExecutionTestFixture(t *testing.T, e *Validator, g materializationExecutionFixture) *materializationExecutionTestContext {
	t.Helper()
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	values := map[string]validation.Value{}
	for id, raw := range map[string][]byte{"provisioning-plan-v1": g.Plan, "backend-manifest-v2": g.Manifest, "runtime-snapshot-v1": g.Actual} {
		v, err := e.Validate(id, raw, limits, nil)
		if err != nil {
			t.Fatalf("owner %s: %v", id, err)
		}
		values[id] = v
	}
	return &materializationExecutionTestContext{snapshot: MaterializationExecutionSnapshot{Plan: values["provisioning-plan-v1"], Manifest: values["backend-manifest-v2"], Actual: values["runtime-snapshot-v1"], Predecessor: g.Predecessor, Submission: []byte(g.Submission)}, original: g.Original.compilation(), current: g.Current.compilation()}
}

func TestMaterializationExecutionBindsIndependentPlanOriginsAndInventory(t *testing.T) {
	e := boundTestOwner(t)
	raw, err := os.ReadFile("testdata/materialization-execution.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []materializationExecutionFixture
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, g := range cases {
		t.Run(g.Name, func(t *testing.T) {
			c := materializationExecutionTestFixture(t, e, g)
			materializationExecutionTestPhases(t, e, c)
			limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
			submission := controlJSON(t, map[string]any{"contract_id": "backend-materialization-attestation-v1", "sdl": g.Submission})
			if _, err := e.Validate("backend-materialization-attestation-v1", submission, limits, c); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Validate("materialized-scenario-v1", g.Current.Document, limits, c); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func materializationOptionalFixture(raw json.RawMessage) []byte {
	if string(raw) == "null" {
		return nil
	}
	return raw
}
func materializationFixtureRows(rows map[string][]json.RawMessage) map[string][][]byte {
	result := map[string][][]byte{}
	for key, items := range rows {
		for _, item := range items {
			result[key] = append(result[key], item)
		}
	}
	return result
}

func materializationExecutionTestPhases(t *testing.T, e *Validator, c *materializationExecutionTestContext) {
	t.Helper()
	r := materializationExecution{owner: e, context: c, snapshot: c.snapshot}
	for _, step := range []struct {
		name  string
		check func() error
	}{
		{"load", r.load}, {"compile", func() error { return r.compile(c.snapshot.Submission) }}, {"binding", r.binding},
		{"origins", func() error { return materializationOrigins(r.original, r.current) }}, {"inventory", r.inventory}, {"nodes", r.nodeBindings},
	} {
		if stepErr := step.check(); stepErr != nil {
			pd, _ := jsonDigest(map[string]any{"domain": r.domain, "plan": materializationPlanProjection(r.plan)})
			sd, _ := jsonDigest(r.previous)
			md, _ := jsonDigest(r.manifest)
			t.Fatalf("phase %s: %v; plan=%s/%s previous=%s/%s manifest=%s/%s", step.name, stepErr, pd, stringAt(r.current.full, "materialization_provenance", "plan_digest"), sd, stringAt(r.current.full, "materialization_provenance", "predecessor_digest"), md, stringAt(r.current.full, "materialization_provenance", "producer", "manifest_digest"))
		}
	}
}
