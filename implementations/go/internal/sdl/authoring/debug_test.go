package authoring

import (
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestSelectedModel(t *testing.T) {
	p, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("../../../../../examples/scenarios/port-authority-surge-response.sdl.yaml")
	if err != nil {
		t.Fatal(err)
	}
	_, err = p.Format(Request{Source: raw})
	if e, ok := errors.AsType[*modelError](err); ok {
		t.Fatalf("path=%s cause=%v", e.path, e.cause)
	}
	if err != nil {
		t.Fatal(err)
	}
}
