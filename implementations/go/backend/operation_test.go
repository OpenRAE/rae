package backend_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/backend"
)

type uncalledProvider struct{ backend.OperationProvider }

func TestOperationOptInChecksContractFamilyWithoutCallingProvider(t *testing.T) {
	declared := []string{"backend-operation-request-v1", "backend-operation-response-v1", "backend-operation-control-v1", "backend-operation-capabilities-v1"}
	if _, err := backend.RequireOperationProvider(uncalledProvider{}, declared); err != nil {
		t.Fatal(err)
	}
	var missing *uncalledProvider
	for _, provider := range []any{nil, missing, struct{}{}} {
		if _, err := backend.RequireOperationProvider(provider, declared); err == nil {
			t.Fatal("missing provider accepted")
		}
	}
	for _, versions := range [][]string{declared[:3], append(append([]string{}, declared...), "unknown-v1"), append(append([]string{}, declared...), declared[0])} {
		if _, err := backend.RequireOperationProvider(uncalledProvider{}, versions); err == nil {
			t.Fatal("invalid contract declaration accepted")
		}
	}
}

type uncalledBridge struct{ backend.MixedBridge }
type uncalledCoordinator struct{ backend.MixedTimeCoordinator }
type uncalledReader struct{ backend.MixedStageReader }

func TestMixedAndInjectRolesRequireIndependentOptIn(t *testing.T) {
	operations := []string{"backend-operation-request-v1", "backend-operation-response-v1", "backend-operation-control-v1", "backend-operation-capabilities-v1"}
	if _, err := backend.RequireInjectOccurrenceProvider(uncalledProvider{}, operations); err == nil {
		t.Fatal("inject role inferred from operations")
	}
	inject := append(append([]string{}, operations...), "inject-occurrence-v1", "inject-occurrence-outcome-v1")
	if _, err := backend.RequireInjectOccurrenceProvider(uncalledProvider{}, inject); err != nil {
		t.Fatal(err)
	}
	mixed := append(append([]string{}, operations...), "mixed-backend-execution-binding-v1", "mixed-backend-stage-report-v1")
	for _, test := range []struct {
		role    string
		service any
	}{{"bridge", uncalledBridge{}}, {"coordinator", uncalledCoordinator{}}, {"reader", uncalledReader{}}} {
		if err := backend.RequireMixedService(test.service, test.role, mixed); err != nil {
			t.Fatal(test.role, err)
		}
		if err := backend.RequireMixedService(test.service, test.role, operations); err == nil {
			t.Fatal("mixed opt-in bypassed")
		}
	}
	if err := backend.RequireMixedService(uncalledReader{}, "bridge", mixed); err == nil {
		t.Fatal("reader treated as bridge")
	}
}
