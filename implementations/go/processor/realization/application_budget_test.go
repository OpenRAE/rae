package realization

import (
	"fmt"
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func applicationBudgetFixture(t *testing.T, count int) (Requirement, []any) {
	t.Helper()
	routes := make([]any, count)
	for index := range routes {
		routes[index] = map[string]any{"route_id": fmt.Sprintf("route-%d", index), "path": fmt.Sprintf("/route-%d", index), "methods": []any{"GET"}, "auth_required": false}
	}
	applications := []any{map[string]any{"application_id": "portal", "framework": "flask", "routes": routes}}
	source := map[string]any{"name": "application-budget", "nodes": map[string]any{"webapp": map[string]any{"type": "compute", "os": "linux", "runtime": map[string]any{"applications": applications}}}}
	compiled := compileRealizationFixture(t, string(requireJSON(t, source)))
	for _, requirement := range compiled.Requirements {
		if requirement.Kind == "runtime-applications" {
			return requirement, applications
		}
	}
	t.Fatal("missing application requirement")
	return Requirement{}, nil
}
func applicationConstraintStatus(t *testing.T, requirement Requirement, input []any, observed bool) string {
	t.Helper()
	if requirement.Constraint == nil || requirement.StructureError {
		t.Fatalf("application authority not representable: %+v", requirement)
	}
	projection, err := ProjectConcern(requirement.Kind, selectionTestValue(t, input), observed, true)
	if err != nil {
		t.Fatal(err)
	}
	result, err := admission.EvaluateRealizationConstraint(requirement.Constraint, projection, admission.DefaultConstraintLimits())
	if err != nil {
		t.Fatal(err)
	}
	return requireType[string](t, requireType[map[string]any](t, result.Document())["status"])
}
func TestApplicationConstraintFitsDefaultBudgetAndKeepsExactRoutes(t *testing.T) {
	// Issue 1759 records route counts 5, 15, 30. Small/intermediate counts also
	// exercise constructor defaults and the first change in each nested scope.
	for _, count := range []int{1, 5, 8, 15, 16, 30} {
		t.Run(strconv.Itoa(count), func(t *testing.T) {
			requirement, applications := applicationBudgetFixture(t, count)
			for _, observed := range []bool{false, true} {
				if status := applicationConstraintStatus(t, requirement, applications, observed); status != "conformant" {
					t.Fatalf("observed=%v status=%s", observed, status)
				}
			}
			routes := requireType[[]any](t, requireType[map[string]any](t, applications[0])["routes"])
			requireType[map[string]any](t, routes[0])["path"] = "/wrong"
			if status := applicationConstraintStatus(t, requirement, applications, true); status != "nonconformant" {
				t.Fatalf("changed route status=%s", status)
			}
		})
	}
}
