package sdl_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestDescriptorProfilesRequireNativeOwner(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	profiles, err := sdl.DescriptorProfiles(scenario)
	if err != nil || len(profiles) != 0 {
		t.Fatalf("profiles=%v %v", profiles, err)
	}
	if _, err := sdl.DescriptorProfiles(replacedDescriptorScenario{scenario}); err == nil {
		t.Fatal("foreign owner accepted")
	}
}

type replacedDescriptorScenario struct{ sdl.Scenario }
