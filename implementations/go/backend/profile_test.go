package backend_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/backend"
)

func TestLoadProfileUsesPackagedAuthorityAndReturnsCopies(t *testing.T) {
	for _, id := range []string{"provisioning-only", "orchestration-capable", "orchestration-evaluation", "full-remote-control-plane", "observability-evidence", "operation-supervision"} {
		p, err := backend.LoadProfile(id)
		if err != nil {
			t.Fatal(id, err)
		}
		actual, _ := p.Profile.Value()
		contracts, _ := p.RequiredContracts.Value()
		if actual != id || len(contracts) == 0 {
			t.Fatal("incorrect authority")
		}
		first := contracts[0]
		contracts[0] = "corrupt"
		again, err := backend.LoadProfile(id)
		if err != nil {
			t.Fatal(err)
		}
		copied, _ := again.RequiredContracts.Value()
		if copied[0] != first {
			t.Fatal("cached profile alias")
		}
	}
	for _, id := range []string{"", "../provisioning-only", "/provisioning-only", "Provisioning-only", "provisioning-only/", "missing-profile", "provisioning-only\n"} {
		if _, err := backend.LoadProfile(id); err == nil {
			t.Fatal("invalid profile accepted", id)
		}
	}
}
