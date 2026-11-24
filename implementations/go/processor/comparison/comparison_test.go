package comparison_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestComparisonCoordinatesUseNativeScenarioOwnership(t *testing.T) {
	source, err := sdl.AuthoredScenario([]byte(`{"name":"arena","version":"1"}`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := comparison.FromScenario(source)
	if err != nil {
		t.Fatal(err)
	}
	coordinate, err := comparison.Coordinate(artifact, "2", nil)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(coordinate.Document())
	if err != nil {
		t.Fatal(err)
	}
	var got struct {
		Identity string `json:"canonical_identity"`
	}
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatal(err)
	}
	if got.Identity != "scenario:arena" {
		t.Fatal(got.Identity)
	}
}
