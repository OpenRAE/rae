package experiment

import (
	"context"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type inspectionPanicError struct{}

func (inspectionPanicError) Error() string { return "private-owner-error" }
func (inspectionPanicError) As(any) bool   { panic("private-owner-inspection") }

type errorInspectionHost struct{ *testHost }

func (*errorInspectionHost) Advance(context.Context, Trial) (Phase, error) {
	return Phase{}, inspectionPanicError{}
}
func TestRuntimeIsolatesForeignErrorInspection(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &errorInspectionHost{testHost: &testHost{}}, &testJournal{}))
	_, err := c.Advance(t.Context(), c.options.Identity)
	category, known := fault.CategoryOf(err)
	if !known || category != fault.Operational || strings.Contains(err.Error(), "private-") {
		t.Fatal("unsafe owner error inspection", err)
	}
}
