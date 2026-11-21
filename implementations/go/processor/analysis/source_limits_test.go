package analysis

import (
	"math"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestAnalysisSourceLimitCannotOverflow(t *testing.T) {
	options := sdl.DefaultParseOptions()
	options.Limits.MaxInputBytes = math.MaxInt64
	input := &SourceInput{Source: sdl.SourceContext{Root: "source.yaml", FS: fstest.MapFS{"source.yaml": &fstest.MapFile{Data: []byte("name: example\n")}}}, Options: options}
	got, err := readAnalysisSource(input)
	if err != nil {
		t.Fatal(err)
	}
	if string(got.RootBytes) != "name: example\n" {
		t.Fatalf("source truncated: %q", got.RootBytes)
	}
	options.Limits.MaxInputBytes = 4
	input.Options = options
	if _, err = readAnalysisSource(input); err == nil {
		t.Fatal("oversize source admitted")
	}
}
