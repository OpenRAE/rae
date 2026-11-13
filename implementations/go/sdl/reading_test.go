package sdl_test

import (
	"math"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestPublicScenarioFileLimitDoesNotOverflow(t *testing.T) {
	options := sdl.DefaultParseOptions()
	options.Limits.MaxInputBytes = math.MaxInt64
	options.Limits.MaxComposedBytes = math.MaxInt64
	scenario, err := sdl.ParseFile(fstest.MapFS{"input.yaml": &fstest.MapFile{Data: []byte("name: bounded\n")}}, "input.yaml", options)
	if err != nil {
		t.Fatal(err)
	}
	if scenario.Document()["name"] != "bounded" {
		t.Fatal("read lost the source")
	}
}
