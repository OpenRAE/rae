package planning

import (
	"encoding/json"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func finiteCapabilityFixture(t *testing.T) (*capabilityDomainIndex, processor.Resource) {
	t.Helper()
	scenario, err := sdl.Parse([]byte(`name: domains
variables:
  family: {type: string, default: linux, allowed_values: [linux, windows]}
  architecture: {type: string, default: amd64, allowed_values: [amd64, arm64]}
  count: {type: integer, default: 1, allowed_values: [1, 4, 2]}
nodes:
  host: {type: compute, os: '${family}', architecture: '${architecture}'}
infrastructure:
  host: {count: '${count}'}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	view := compiled.Model().View()
	index, err := newCapabilityDomains(view)
	if err != nil {
		t.Fatal(err)
	}
	for _, resource := range view.Resources {
		if resource.Address == "provision.node.host" {
			return index, resource
		}
	}
	t.Fatal("missing compiled node")
	return nil, processor.Resource{}
}

func TestFiniteCapabilityDomainsRetainAllChoicesAndMaximumNodeCount(t *testing.T) {
	index, resource := finiteCapabilityFixture(t)
	domain, finding := index.domain(resource, termOsFamily, "nodes.os", "linux")
	if finding != nil || !slices.Equal(domain, []string{"linux", "windows"}) {
		t.Fatalf("finite OS domain changed: %v %+v", domain, finding)
	}
	if got := index.scalarSupport(resource, termOsFamily, "nodes.os", "linux", []string{"windows"}, false); len(got) != 0 {
		t.Fatal("feasible alternative OS was not retained")
	}
	if got := index.scalarSupport(resource, termOsFamily, "nodes.os", "linux", []string{"other"}, false); len(got) != 1 || got[0].Code != "provisioner.unsupported-os-family" {
		t.Fatalf("unsupported domain accepted: %+v", got)
	}
	if got := index.scalarSupport(resource, "node-architecture", "nodes.architecture", "amd64", []string{"amd64"}, true); len(got) != 1 || got[0].Code != "provisioner.unsupported-node-architecture" {
		t.Fatalf("partial architecture support accepted: %+v", got)
	}
	maximum, finding := index.count(resource)
	if finding != nil || maximum == nil || maximum.String() != "4" {
		t.Fatalf("selected count replaced finite maximum: %v %+v", maximum, finding)
	}
	bad := index.constraints[[2]string{resource.Address, "nodes.os"}]
	bad.AllowedValues = []processor.Scalar{{}}
	index.constraints[[2]string{resource.Address, "nodes.os"}] = bad
	if _, finding := index.domain(resource, termOsFamily, "nodes.os", "linux"); finding == nil || finding.Code != "provisioner.os-family-variable-domain-invalid" {
		t.Fatalf("invalid scalar domain accepted: %+v", finding)
	}
	count := index.constraints[[2]string{resource.Address, "infrastructure.count"}]
	count.AllowedValues = bad.AllowedValues
	index.constraints[[2]string{resource.Address, "infrastructure.count"}] = count
	if _, finding := index.count(resource); finding == nil || finding.Code != "provisioner.count-variable-domain-invalid" {
		t.Fatalf("invalid count domain accepted: %+v", finding)
	}
}

func TestConcreteCapabilityFallbacksPreserveMissingAndUnboundValues(t *testing.T) {
	index, resource := finiteCapabilityFixture(t)
	index.constraints = map[[2]string]processor.CapabilityConstraint{}
	for _, test := range []struct {
		concrete string
		want     []string
		invalid  bool
	}{{"linux", []string{"linux"}, false}, {"", nil, false}, {"${missing}", nil, true}} {
		got, finding := index.domain(resource, termOsFamily, "nodes.os", test.concrete)
		if !slices.Equal(got, test.want) || (finding != nil) != test.invalid {
			t.Fatalf("concrete domain=%v %+v", got, finding)
		}
	}
	if resource.Node == nil {
		t.Fatal("node details missing")
	}
	node := *resource.Node
	resource.Node = &node
	for _, test := range []struct {
		number string
		want   string
	}{{"7", "7"}, {"invalid", ""}} {
		number := json.Number(test.number)
		resource.Node.Count = &number
		count, finding := index.count(resource)
		if finding != nil || test.want == "" && count != nil || test.want != "" && (count == nil || count.String() != test.want) {
			t.Fatalf("concrete count=%v %+v", count, finding)
		}
	}
	resource.Node.Count = nil
	count, finding := index.count(resource)
	if finding != nil || count.String() != "1" {
		t.Fatal("missing count lost its singleton default")
	}
}
