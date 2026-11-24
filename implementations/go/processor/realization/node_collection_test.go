package realization_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestNodeCollectionNeedsEnclosingAuthority(t *testing.T) {
	for _, test := range []struct {
		name, designation string
		admits            bool
	}{
		{"closed", "", false},
		{"child-open", "realization: {default: closed, scopes: [{field_pointer: /nodes/host, posture: open}]}\n", false},
		{"parent-open", "realization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}]}\n", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			scenario, err := sdl.Parse([]byte("name: example\nnodes: {host: {type: compute}}\n"+test.designation), sdl.DefaultParseOptions())
			requireNoError(t, err)
			instance, err := sdl.Instantiate(scenario, nil)
			requireNoError(t, err)
			members := []realization.NodeCollectionMember{{Address: "provision.node.host", Kind: "node", Name: "host"}}
			authority, err := realization.CompileNodeCollection(instance, members)
			if err != nil || authority == nil {
				t.Fatalf("authority=%v %v", authority, err)
			}
			members = append(members, realization.NodeCollectionMember{Address: "provision.node.worker", Kind: "node", Name: "worker"})
			admitted, err := realization.NodeCollectionAdmits(authority, members)
			if err != nil || admitted != test.admits {
				t.Fatalf("additional member admitted=%v %v", admitted, err)
			}
			members[len(members)-1].Name = "foreign.worker"
			admitted, err = realization.NodeCollectionAdmits(authority, members)
			if err != nil || admitted {
				t.Fatalf("undeclared namespace admitted=%v %v", admitted, err)
			}
		})
	}
}
