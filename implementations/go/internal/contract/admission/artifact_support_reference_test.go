package admission

import (
	"encoding/json"
	"testing"
)

func TestArtifactPreparationRequiresExactRoutesAndAvailability(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name                   string
			Artifact, Declarations json.RawMessage
			Admitted               bool
		}
	}
	readFullReferenceJSON(t, "testdata/artifact-support-verdicts.json", &reference)
	if len(reference.Cases) != 10 {
		t.Fatal("artifact support inventory changed")
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			artifact := decodeRuleObject(t, string(c.Artifact))
			declarations := array(decodeRuleObject(t, string(c.Declarations)))
			err := materializationArtifactSupport(artifact, declarations, "source-artifact")
			if (err == nil) != c.Admitted {
				t.Fatalf("artifact preparation differs from native support (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}
