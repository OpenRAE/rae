package admission

import (
	"encoding/json"
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type studyReferenceOwner struct{ tasks, runs [][]byte }

func (c studyReferenceOwner) ExperimentTasks() [][]byte { return c.tasks }
func (c studyReferenceOwner) ExperimentRuns() [][]byte  { return c.runs }
func TestStudyContextJoinsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Documents map[string]json.RawMessage
		Cases     []struct {
			Study       string
			Tasks, Runs []string
			Admitted    bool
		}
	}
	readFullReferenceJSON(t, "testdata/study-context-verdicts.json", &reference)
	if len(reference.Cases) != 17 || len(reference.Documents) != 18 {
		t.Fatal("study reference inventory changed")
	}
	e := boundTestOwner(t)
	resolve := func(ids []string) [][]byte {
		raw := make([][]byte, len(ids))
		for n, id := range ids {
			var ok bool
			raw[n], ok = reference.Documents[id]
			if !ok {
				t.Fatal("missing study source")
			}
		}
		return raw
	}
	for n, c := range reference.Cases {
		t.Run(strconv.Itoa(n), func(t *testing.T) {
			raw := resolve([]string{c.Study})[0]
			err := e.studyJoins(validation.Invocation{Instance: decodeRuleObject(t, string(raw)), Context: studyReferenceOwner{resolve(c.Tasks), resolve(c.Runs)}})
			if (err == nil) != c.Admitted {
				t.Fatalf("study context differs from native validation (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}
