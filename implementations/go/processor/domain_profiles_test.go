package processor_test

import (
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestDomainProfileHasOneDesignatedControllerOwner(t *testing.T) {
	raw, err := os.ReadFile("testdata/domain-profile-controllers.json")
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	selections := map[string]int{}
	for _, resource := range compiled.Model().View().Resources {
		if len(resource.SelectedProfiles) > 0 {
			selections[resource.Address] = len(resource.SelectedProfiles)
		}
	}
	if len(selections) != 1 || selections["provision.domain-controller.corp.dc"] != 1 {
		t.Fatalf("domain profile must belong only to designated controller: %v", selections)
	}
}
