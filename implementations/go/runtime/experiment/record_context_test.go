package experiment

import (
	"maps"
	"testing"
)

func TestRuntimeRecordValidationSelectsOnlyPinnedApparatus(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	slot := c.slotSnapshot()[0]
	source := recordSourceForSlot(t, slot, ref.Case)
	expected, err := c.recordContext(source)
	if err != nil {
		t.Fatal(err)
	}
	for key, manifest := range maps.Clone(c.options.Inputs.ApparatusManifests) {
		unused := key
		unused.ComponentName = "unused-" + key.ComponentName
		c.options.Inputs.ApparatusManifests[unused] = manifest
	}
	actual, err := c.recordContext(source)
	if err != nil {
		t.Fatal(err)
	}
	if string(actual.processor) != string(expected.processor) || string(actual.backend) != string(expected.backend) {
		t.Fatal("unused apparatus changed record authority")
	}
}
