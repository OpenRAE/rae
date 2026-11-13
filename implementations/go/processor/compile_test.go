package processor_test

import (
	"encoding/json"
	"strconv"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileTypedNodesAndDependencies(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\nnodes:\n  lan: {type: switch}\n  server: {type: compute, os: linux}\ninfrastructure:\n  lan: {}\n  server: {links: [lan], count: 2}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	if result.Nodes() != 1 || result.Networks() != 1 {
		t.Fatalf("compiled counts = %d, %d", result.Nodes(), result.Networks())
	}
	view := result.Model().View()
	if view.Name != "example" || len(view.Resources) != 2 {
		t.Fatalf("compiled resources = %#v", view)
	}
	resource := compiledTestResource(t, view.Resources, "provision.node.server")
	if resource.Node == nil || resource.Node.OSFamily != "linux" || resource.Node.Count == nil || *resource.Node.Count != "2" {
		t.Fatalf("node capability facts=%#v", resource.Node)
	}
	if len(resource.OrderingDependencies) != 1 || resource.OrderingDependencies[0] != "provision.network.lan" {
		t.Fatalf("ordering dependencies=%v", resource.OrderingDependencies)
	}
	resource.Node.OSFamily = "changed"
	resource.OrderingDependencies[0] = "changed"
	clear(resource.Payload.JSON())
	unchanged := compiledTestResource(t, result.Model().View().Resources, "provision.node.server")
	if unchanged.Node.OSFamily != "linux" || unchanged.OrderingDependencies[0] != "provision.network.lan" || len(unchanged.Payload.JSON()) == 0 {
		t.Fatal("compiled model retained caller mutations")
	}
}

func compiledTestResource(t *testing.T, resources []processor.Resource, address string) processor.Resource {
	t.Helper()
	for _, resource := range resources {
		if resource.Address == address {
			return resource
		}
	}
	t.Fatal("missing resource", address)
	return processor.Resource{}
}

type foreignCompilation struct{ processor.Compilation }

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (foreignCompilation) Model() processor.RuntimeModel { panic("foreign compilation called") }

type foreignModel struct{ processor.RuntimeModel }

func (foreignModel) View() processor.CompiledScenario { panic("foreign model called") }
func TestCompileOwnerRefusesForeignHandles(t *testing.T) {
	for _, input := range []processor.Compilation{nil, foreignCompilation{}} {
		if _, err := processor.AdmitCompilation(input); err == nil {
			t.Fatal("foreign compilation accepted")
		}
	}
	for _, input := range []processor.RuntimeModel{nil, foreignModel{}} {
		if _, err := processor.AdmitRuntimeModel(input); err == nil {
			t.Fatal("foreign model accepted")
		}
	}
	if _, err := processor.Compile(nil, nil); err == nil {
		t.Fatal("nil scenario accepted")
	}
}

func TestCompileIncludesRealizationWithoutSharingAuthorityViews(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\nnodes:\n  server: {type: compute, os: linux}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	view := result.Model().View()
	if len(view.RealizationRequirements) < 3 || len(view.RealizationAuthority) != 68 {
		t.Fatalf("missing realization: %d requirements, %d authorities", len(view.RealizationRequirements), len(view.RealizationAuthority))
	}
	*view.RealizationRequirements[0].Posture = "changed"
	view.RealizationAuthority[0].PayloadPath[0] = "changed"
	if *result.Model().View().RealizationRequirements[0].Posture == "changed" || result.Model().View().RealizationAuthority[0].PayloadPath[0] == "changed" {
		t.Fatal("caller changed owned authority")
	}
	document := result.Document()
	requirements, ok := document["realization_requirements"].([]any)
	if !ok || len(requirements) != len(view.RealizationRequirements) {
		t.Fatal("compiled projection dropped realization")
	}
	if requireType[map[string]any](t, requirements[0])["requirement_kind"] != "compute-substrate" {
		t.Fatal("requirement projection order or field names changed")
	}
}

func TestCompileTimeRetainsExactRatiosAndControlFacts(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: timed
nodes:
  server: {type: compute}
time_domains:
  scenario:
    kind: simulated
    tick_period_seconds: {numerator: 1, denominator: 1000}
    epoch: scenario_start
    visibility: participant_visible
    description: scenario milliseconds
clocks:
  clock:
    time_domain_ref: scenario
    authority_kind: runtime
    authority_ref: runtime.time-coordinator
    monotonicity: non_decreasing
    supports_pause: true
    supports_reset: true
    description: scenario clock
time_progression_policies:
  policy:
    clock_ref: clock
    advancement_mode: stepped
    synchronization_mode: barrier
    step_ticks: 10
    reset_behavior: new_segment_zero
    replay_behavior: restore_recorded_advances
    description: deterministic progression
temporal_constraints:
  window:
    constraint_kind: window
    clock_ref: clock
    subject_refs: [nodes.server]
    start: {tick: 10}
    end: {tick: 100}
    description: server window
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	view := result.Model().View()
	if len(view.TimeModel.Domains) != 1 || view.TimeModel.Domains[0].TickDenominator != "1000" || !view.TimeModel.Clocks[0].SupportsPause {
		t.Fatalf("time facts = %#v", view.TimeModel)
	}
	if view.TimeModel.Constraints[0].SubjectAddresses[0] != "sdl.nodes.server" {
		t.Fatalf("time subject = %v", view.TimeModel.Constraints[0].SubjectAddresses)
	}
	wire, err := processor.TimeModelContract(result)
	if err != nil || wire == nil {
		t.Fatalf("time contract = %v, %v", wire, err)
	}
	options, err := processor.CompiledComponentOptions(result.Model())
	if err != nil || !options.WithTime {
		t.Fatalf("component options = %v, %v", options, err)
	}
	*view.TimeModel.ProgressionPolicies[0].StepTicks = "99"
	if *result.Model().View().TimeModel.ProgressionPolicies[0].StepTicks != "10" {
		t.Fatal("time view retained pointer mutation")
	}
}

func TestCompileKeepsOrderingAndRefreshMeaningSeparate(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: evaluation
nodes:
  server:
    type: compute
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: declared runtime
    subjects: [nodes.server]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  ready: {proposition: health, role: precondition}
events:
  check: {assertions: [ready]}
scripts:
  sequence: {start_time: 0, end_time: 60, speed: 1, events: {check: 0}}
stories:
  story: {scripts: [sequence]}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	resources := map[string]processor.Resource{}
	for _, resource := range result.Model().View().Resources {
		resources[resource.Address] = resource
	}
	condition := resources["evaluation.condition.server.health"]
	if len(condition.OrderingDependencies) != 0 || len(condition.RefreshDependencies) != 1 || condition.RefreshDependencies[0] != "provision.node.server" {
		t.Fatalf("condition dependencies = %v / %v", condition.OrderingDependencies, condition.RefreshDependencies)
	}
	event := resources["orchestration.event.check"]
	if len(event.OrderingDependencies) != 0 || len(event.RefreshDependencies) != 1 || event.RefreshDependencies[0] != "evaluation.assertion.ready" {
		t.Fatalf("event dependencies = %v / %v", event.OrderingDependencies, event.RefreshDependencies)
	}
	if resources["evaluation.proposition.health"].Evaluation.PredicateKind != "presence" {
		t.Fatal("missing typed evaluation facts")
	}
	if resources["orchestration.script.sequence"].OrderingDependencies[0] != "orchestration.event.check" || resources["orchestration.story.story"].OrderingDependencies[0] != "orchestration.script.sequence" {
		t.Fatal("narrative references were not lowered")
	}
}

func TestCompileFiniteCapabilityDomainKeepsSourceBudget(t *testing.T) {
	values := make([]string, 5000)
	for i := range values {
		values[i] = strconv.Itoa(i + 1)
	}
	input := "name: finite\nvariables:\n  count: {type: integer, default: 1, allowed_values: [" + strings.Join(values, ",") + "]}\nnodes:\n  server: {type: compute}\ninfrastructure:\n  server: {count: '${count}'}\n"
	scenario, err := sdl.Parse([]byte(input), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	constraints := compiled.Model().View().CapabilityConstraints
	if len(constraints) != 1 || len(constraints[0].AllowedValues) != 5000 {
		t.Fatalf("finite domain lost values: %d constraints", len(constraints))
	}
	if constraints[0].AllowedValues[4999].Kind() != "integer" || requireType[json.Number](t, constraints[0].AllowedValues[4999].Value()) != "5000" {
		t.Fatal("finite domain changed scalar kind or value")
	}
}
