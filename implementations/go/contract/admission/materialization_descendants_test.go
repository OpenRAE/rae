package admission

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type materializationRetainedFixture struct {
	SDL    string                      `json:"SDL"`
	Phase  materializationPhaseFixture `json:"Phase"`
	Record json.RawMessage             `json:"Record"`
}
type materializationInventoryFixture struct {
	materializationExecutionFixture

	Envelope json.RawMessage                  `json:"Envelope"`
	Retained []materializationRetainedFixture `json:"Retained"`
}
type materializationInventoryTestContext struct {
	*materializationExecutionTestContext

	envelope validation.Value
	retained []materializationRetainedFixture
}

func (c *materializationInventoryTestContext) MaterializationEnvelope() validation.Value {
	return c.envelope
}
func (c *materializationInventoryTestContext) CompileMaterialization(request MaterializationCompileRequest) (MaterializationCompilation, error) {
	for _, item := range c.retained {
		if digest.SHA256(request.Source) == item.Phase.SourceSHA256 {
			return item.Phase.compilation(), nil
		}
	}
	return c.materializationExecutionTestContext.CompileMaterialization(request)
}
func (c *materializationInventoryTestContext) RetainedMaterializationSDL(record json.RawMessage) ([]byte, error) {
	v, err := materializationJSON(record)
	if err != nil {
		return nil, err
	}
	for _, item := range c.retained {
		candidate, parseErr := materializationJSON(item.Record)
		if parseErr != nil {
			return nil, parseErr
		}
		if equal(candidate, v) {
			return []byte(item.SDL), nil
		}
	}
	return nil, errors.New("private-protected-archive-refusal")
}
func materializationInventoryTestFixture(t *testing.T, e *Validator, g materializationInventoryFixture) *materializationInventoryTestContext {
	t.Helper()
	envelope, err := e.Validate("realization-envelope-v1", g.Envelope, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	return &materializationInventoryTestContext{materializationExecutionTestContext: materializationExecutionTestFixture(t, e, g.materializationExecutionFixture), envelope: envelope, retained: g.Retained}
}
func TestMaterializationInventoryBindsLineageAndLifecycleToProtectedPredecessor(t *testing.T) {
	e := boundTestOwner(t)
	raw, err := os.ReadFile("testdata/materialization-inventory.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []materializationInventoryFixture
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, g := range cases {
		t.Run(g.Name, func(t *testing.T) {
			c := materializationInventoryTestFixture(t, e, g)
			materializationInventoryTestPhases(t, e, c)
			document, err := materializationJSON(g.Current.FullDocument)
			if err != nil {
				t.Fatal(err)
			}
			report := at(document, "materialization_provenance", "inventory")
			if _, err = e.Validate("backend-runtime-descendants-v1", controlJSON(t, report), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, c); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func materializationInventoryTestPhases(t *testing.T, e *Validator, c *materializationInventoryTestContext) {
	t.Helper()
	r := materializationInventory{context: c, execution: materializationExecution{owner: e, context: c, snapshot: c.snapshot}}
	if err := r.execution.load(); err != nil {
		t.Fatalf("load: %v", err)
	}
	if err := r.execution.compile(c.snapshot.Submission); err != nil {
		t.Fatalf("compile: %v", err)
	}
	r.report = at(r.execution.current.full, "materialization_provenance", "inventory")
	r.originals = materializationScope(r.execution.original.resources, "provisioning")
	for _, step := range []struct {
		name  string
		check func() error
	}{
		{"report", r.boundReport}, {"binding", r.execution.binding}, {"predecessor", r.predecessor}, {"lineage", r.lineage}, {"project", r.project}, {"membership", r.membership}, {"capabilities", r.capabilities}, {"augmentation", r.augmentation},
	} {
		if err := step.check(); err != nil {
			t.Fatalf("phase %s: %v", step.name, err)
		}
	}
}
