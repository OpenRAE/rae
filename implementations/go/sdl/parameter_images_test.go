package sdl_test

import (
	"fmt"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const parameterImageScenario = `name: derived
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
`

func TestParameterImagesKeepRepeatedFiniteInput(t *testing.T) {
	scenario, err := sdl.Parse([]byte(parameterImageScenario), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	image, present, err := sdl.ParameterDerivationImage(instance, "/nodes/host/runtime/applications/0/routes/0/path")
	if err != nil {
		t.Fatal(err)
	}
	if !present || image == nil {
		t.Fatal("finite image missing")
	}
	values := requireType[[]any](t, image.Document())
	if len(values) != 2 || values[0] != "/blue/blue" || values[1] != "/green/green" {
		t.Fatalf("values=%v", values)
	}
}

func TestParameterImageBoundaries(t *testing.T) {
	for _, test := range []struct {
		name, source string
		invalid      bool
	}{
		{"unbounded", strings.Replace(parameterImageScenario, ", allowed_values: [blue, green]", "", 1), false},
		{"independent-finite", strings.Replace(strings.Replace(parameterImageScenario, "nodes:", "  other: {type: string, default: blue, allowed_values: [blue, green]}\nnodes:", 1), "/${value}/${value}", "/${value}/${other}", 1), true},
	} {
		t.Run(test.name, func(t *testing.T) {
			scenario, err := sdl.Parse([]byte(test.source), sdl.DefaultParseOptions())
			if err != nil {
				t.Fatal(err)
			}
			instance, err := sdl.Instantiate(scenario, nil)
			if err != nil {
				t.Fatal(err)
			}
			image, found, err := sdl.ParameterDerivationImage(instance, "/nodes/host/runtime/applications/0/routes/0/path")
			if !found || (err != nil) != test.invalid || image != nil {
				t.Fatalf("image=%v found=%v error=%v", image, found, err)
			}
			if _, _, err := sdl.ParameterDerivationImage(replacedDescriptorScenario{instance}, "/nodes/host/runtime/applications/0/routes/0/path"); err == nil {
				t.Fatal("foreign owner accepted")
			}
		})
	}
}

func TestParameterImageKeepsFiniteMemberLimit(t *testing.T) {
	choices := make([]string, 4097)
	for i := range choices {
		choices[i] = fmt.Sprintf("v%d", i)
	}
	source := strings.Replace(parameterImageScenario, "default: blue, allowed_values: [blue, green]", "default: v0, allowed_values: ["+strings.Join(choices, ",")+"]", 1)
	scenario, err := sdl.Parse([]byte(source), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, found, err := sdl.ParameterDerivationImage(instance, "/nodes/host/runtime/applications/0/routes/0/path"); !found || err == nil {
		t.Fatalf("finite member limit lost: found=%v error=%v", found, err)
	}
}

func TestParameterImageUsesArrayItemConstructor(t *testing.T) {
	source := strings.Replace(parameterImageScenario, "    runtime:\n", "    runtime:\n      software_components: [{component_id: tool, name: tool, installed_paths: ['/opt/${value}']}]\n", 1)
	scenario, err := sdl.Parse([]byte(source), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	image, found, err := sdl.ParameterDerivationImage(instance, "/nodes/host/runtime/software_components/0/installed_paths/0")
	if err != nil || !found || image == nil {
		t.Fatalf("array item image=%v found=%v error=%v", image, found, err)
	}
	values := requireType[[]any](t, image.Document())
	if len(values) != 2 || values[0] != "/opt/blue" || values[1] != "/opt/green" {
		t.Fatalf("path images=%v", values)
	}
}
