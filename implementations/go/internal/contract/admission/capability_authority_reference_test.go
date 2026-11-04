package admission

import (
	"slices"
	"testing"
)

func TestCapabilityAuthoritySetsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind, Key string
			Values    []string
		}
	}
	readFullReferenceJSON(t, "testdata/capability-authority-reference.json", &reference)
	if len(reference.Cases) != 49 {
		t.Fatal("authority reference inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Kind+"/"+c.Key, func(t *testing.T) {
			var got []string
			switch c.Kind {
			case "contracts":
				got = supportedManifestContracts(c.Key)
			case "participant":
				got = participantFeatureContracts(c.Key)
			case "time":
				got = timeCapabilityTerms(c.Key)
			case "distribution":
				if family := coreDistributionFamily(c.Key); family != "" {
					got = []string{family}
				}
			default:
				t.Fatal("unknown authority table")
			}
			slices.Sort(got)
			if !slices.Equal(got, c.Values) {
				t.Fatalf("authority differs: got %v want %v", got, c.Values)
			}
		})
	}
}
