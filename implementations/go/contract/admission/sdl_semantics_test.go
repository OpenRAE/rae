package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestSDLLocalSemanticBoundary(t *testing.T) {
	owner := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 4096}
	valid := []byte(`{"name":"example"}`)
	if err := owner.CheckSDLLocalSemantics("sdl-authoring-input-v1", valid, limits); err != nil {
		t.Fatal(err)
	}
	orphan := []byte(`{"name":"example","generated_artifacts":{"a":{"generator":"certificate_bundle","lifecycle":"regenerate_on_change","provenance":"test","outputs":[{"name":"out","path":"cert","sensitivity":"public"}],"consumers":[]}}}`)
	if err := owner.CheckSDLConstruction("sdl-authoring-input-v1", "#", orphan, limits); err != nil {
		t.Fatalf("construction applied a later semantic rule: %v", err)
	}
	if owner.CheckSDLLocalSemantics("sdl-authoring-input-v1", orphan, limits) == nil {
		t.Fatal("semantic admission accepted an orphaned generated artifact")
	}
	if owner.CheckSDLLocalSemantics("missing", valid, limits) == nil || owner.CheckSDLLocalSemantics("sdl-authoring-input-v1", []byte(`{"name":"a","name":"b"}`), limits) == nil {
		t.Fatal("semantic boundary accepted an unknown contract or duplicate input")
	}
	for _, absent := range []*Validator{nil, {}} {
		if absent.CheckSDLLocalSemantics("sdl-authoring-input-v1", valid, limits) == nil {
			t.Fatal("uninitialized semantic owner accepted input")
		}
	}
}
