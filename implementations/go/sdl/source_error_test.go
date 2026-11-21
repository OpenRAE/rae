package sdl_test

import (
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestPublicSourceRefusalRetainsStructuredDiagnostics(t *testing.T) {
	_, err := sdl.ParseWithContext(t.Context(), []byte("name: first\nname: second\n"), sdl.DefaultParseOptions())
	var structured diagnostic.Error
	if !errors.As(err, &structured) {
		t.Fatalf("missing structured refusal: %v", err)
	}
	rows := structured.Diagnostics()
	if len(rows) != 1 || rows[0].Stage != "parse" || rows[0].Pointer != "/name" || rows[0].Range == nil || structured.Code() != rows[0].Code {
		t.Fatalf("source metadata lost: %#v", rows)
	}
	rows[0].Range.StartLine = 999
	if structured.Diagnostics()[0].Range.StartLine == 999 {
		t.Fatal("diagnostic range aliases native state")
	}
}
