package admission

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type satisfiabilityCompilerOwner struct {
	phase        MaterializationCompilation
	fail, mutate bool
}

func (c *satisfiabilityCompilerOwner) CompileMaterialization(request MaterializationCompileRequest) (MaterializationCompilation, error) {
	if c.fail {
		return MaterializationCompilation{}, errors.New("private-owner-detail")
	}
	if request.ContractID != "instantiated-scenario-v1" || digest.SHA256(request.Source) != c.phase.SourceSHA256 {
		return MaterializationCompilation{}, errors.New("wrong witness source")
	}
	if c.mutate {
		request.Source[0] = '!'
	}
	return c.phase, nil
}
func (c *satisfiabilityCompilerOwner) NormalizeMaterializationNode(MaterializationNodeProjection) (json.RawMessage, error) {
	return nil, errors.New("unexpected witness node projection")
}

func TestSatisfiabilityWitnessUsesTheNativeOwner(t *testing.T) {
	raw, err := os.ReadFile("testdata/satisfiable-witness-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Owner materializationPhaseFixture `json:"owner"`
		Cases []struct {
			Name     string          `json:"name"`
			Input    json.RawMessage `json:"input"`
			Admitted bool            `json:"admitted"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(raw, &reference); err != nil {
		t.Fatal(err)
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			owner := &satisfiabilityCompilerOwner{phase: reference.Owner.compilation()}
			result, err := e.Validate("scenario-satisfiability-evidence-v1", c.Input, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, owner)
			if (err == nil) != c.Admitted {
				t.Fatalf("Python admitted=%v: %v", c.Admitted, err)
			}
			if err != nil && result.ContractID() != "" {
				t.Fatal("refusal returned admission")
			}
		})
	}
	for _, owner := range []any{nil, (*satisfiabilityCompilerOwner)(nil), &satisfiabilityCompilerOwner{phase: reference.Owner.compilation(), fail: true}, &satisfiabilityCompilerOwner{phase: reference.Owner.compilation(), mutate: true}, &satisfiabilityCompilerOwner{}} {
		result, err := e.Validate("scenario-satisfiability-evidence-v1", reference.Cases[0].Input, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, owner)
		if err == nil || result.ContractID() != "" || strings.Contains(err.Error(), "private-owner-detail") {
			t.Fatal("missing, changed or failing owner escaped the witness boundary")
		}
	}
}
