package realization

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestPublicParameterImageRemainsEnforceable(t *testing.T) {
	result := compileRealizationFixture(t, `name: derived
variables:
  value: {type: string, default: blue, allowed_values: [blue, green]}
nodes:
  host:
    type: compute
    services: [{name: http, port: 8080, protocol: tcp}]
    runtime:
      applications:
        - application_id: api
          service: http
          protocol: http
          name: API
          routes:
            - route_id: main
              path: '/${value}/${value}'
              methods: [GET]
              responses: [{status_code: 200}]
`)
	for _, requirement := range result.Requirements {
		if requirement.Kind != "runtime-applications" {
			continue
		}
		if requirement.Constraint == nil || requirement.StructureError {
			t.Fatalf("public parameter lost authority: %+v", requirement)
		}
		projection, err := ProjectConcern(requirement.Kind, requirement.source.value, false, true)
		requireNoError(t, err)
		actual := requireType[[]any](t, projection.Document())
		route := requireType[map[string]any](t, requireType[[]any](t, requireType[map[string]any](t, actual[0])["routes"])[0])
		for _, path := range []string{"/green/green", "/blue/green"} {
			route["path"] = path
			value, err := requirement.source.input.valueFragment(actual)
			requireNoError(t, err)
			checked, err := admission.EvaluateRealizationConstraint(requirement.Constraint, value, admission.DefaultConstraintLimits())
			requireNoError(t, err)
			conformant := requireType[map[string]any](t, checked.Document())["status"] == "conformant"
			if conformant != (path == "/green/green") {
				t.Fatalf("path %s relation=%v", path, checked.Document())
			}
		}
		return
	}
	t.Fatal("application requirement missing")
}
