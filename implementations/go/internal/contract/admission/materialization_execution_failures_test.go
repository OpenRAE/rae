package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestMaterializationExecutionRefusesSubstitutedPhaseOwners(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var fixtures []materializationExecutionFixture
	readFullReferenceJSON(t, "testdata/materialization-execution.json", &fixtures)
	fixture := fixtures[0]
	for _, name := range []string{"plan", "manifest", "actual", "predecessor-json", "predecessor-version", "predecessor-shape", "original-source", "current-source", "original-resource", "current-resource", "original-document", "current-document", "original-full", "current-full", "submission", "candidate-source"} {
		t.Run(name, func(t *testing.T) {
			c := materializationExecutionTestFixture(t, e, fixture)
			candidate := map[string]any{"sdl": fixture.Submission}
			switch name {
			case "plan":
				c.snapshot.Plan = validation.Value{}
			case "manifest":
				c.snapshot.Manifest = validation.Value{}
			case "actual":
				c.snapshot.Actual = validation.Value{}
			case "predecessor-json":
				c.snapshot.Predecessor = []byte("{")
			case "predecessor-version":
				c.snapshot.Predecessor = []byte(`{"schema_version":"runtime-snapshot/v1"}`)
			case "predecessor-shape":
				c.snapshot.Predecessor = []byte(`{"hidden":true}`)
			case "original-source":
				c.original.SourceSHA256 = "sha256:foreign"
			case "current-source":
				c.current.SourceSHA256 = "sha256:foreign"
			case "original-resource":
				c.original.Resources = [][]byte{[]byte("{")}
			case "current-resource":
				c.current.Resources = [][]byte{[]byte("{")}
			case "original-document":
				c.original.Document = []byte("{")
			case "current-document":
				c.current.Document = []byte("{")
			case "original-full":
				c.original.FullDocument = []byte("{")
			case "current-full":
				c.current.FullDocument = []byte("{")
			case "submission":
				c.snapshot.Submission = []byte("foreign")
			case "candidate-source":
				candidate["sdl"] = "foreign"
			}
			err := e.materializationExecutionCheck(validation.Invocation{Key: validation.Key{ContractID: "backend-materialization-attestation-v1"}, Instance: candidate, Context: c})
			if err == nil {
				t.Fatal("substituted materialization phase was admitted")
			}
		})
	}
}
