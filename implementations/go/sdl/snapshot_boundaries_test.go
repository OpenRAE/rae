package sdl_test

import (
	"context"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const anyDigest = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

func TestSnapshotAdmissionRefusesUnusableInput(t *testing.T) {
	cancelled, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := sdl.AdmitSnapshotWithContext(cancelled, []byte(`{}`), anyDigest); err == nil {
		t.Fatal("got nil error, want a cancelled admission refused")
	}
	for name, raw := range map[string]string{
		"malformed JSON":       `{`,
		"unknown profile":      `{"profile":"other","scenario":{}}`,
		"extra member":         `{"profile":"raes-sdl-instantiated-snapshot/v3","scenario":{},"x":1}`,
		"scenario not object":  `{"profile":"raes-sdl-instantiated-snapshot/v3","scenario":[]}`,
		"current not instance": `{"profile":"raes-sdl-instantiated-snapshot/v3","scenario":{"name":"plain"}}`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := sdl.AdmitSnapshotWithContext(t.Context(), []byte(raw), anyDigest); err == nil {
				t.Fatal("got nil error, want the snapshot refused")
			}
		})
	}
}

func TestLegacySnapshotMigrationRefusesUnboundChanges(t *testing.T) {
	for name, raw := range map[string]string{
		// A historical VM node needs instantiation provenance for its migration constraint.
		"vm without provenance": `{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{"name":"x","nodes":{"host":{"type":"vm"}}}}`,
		"vm constraints not array": `{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{"name":"x","nodes":{"host":{"type":"vm"}},` +
			`"instantiation_provenance":{"realization_constraints":{}}}}`,
		// Empty legacy classifications change the document, so an unrelated digest cannot authorize them.
		"empty nested classifications": `{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{"name":"x",` +
			`"entities":{"team":{"categories":[],"entities":{"member":{"vulnerabilities":[]}}}},` +
			`"nodes":{"host":{"type":"compute","runtime":{"applications":[{"routes":[{"vulnerability_refs":[]}]}]}}}}}`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := sdl.AdmitSnapshotWithContext(t.Context(), []byte(raw), anyDigest); err == nil {
				t.Fatal("got nil error, want the legacy snapshot refused")
			}
		})
	}
}
