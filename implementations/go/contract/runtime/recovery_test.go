package runtime_test

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

func TestRecoveryObservationsKeepClosedClassificationAndSnapshotRules(t *testing.T) {
	request := runtimecontract.RecoveryObservationRequest{OperationID: strings.Repeat("é", 256), OperationKind: "provisioning", TargetScope: "target", RunScope: "run", RequestCommitment: "sha256:" + strings.Repeat("a", 64)}
	if err := request.Validate(); err != nil {
		t.Fatal(err)
	}
	request.OperationID += "é"
	if request.Validate() == nil {
		t.Fatal("text bound lost")
	}
	request.OperationID = "operation"
	request.RequestCommitment = "sha256:" + strings.Repeat("A", 64)
	if request.Validate() == nil {
		t.Fatal("noncanonical commitment accepted")
	}
	result := runtimecontract.RecoveryObservationResult{Classification: "effect-absent", OperationID: "operation", RequestCommitment: "sha256:" + strings.Repeat("a", 64)}
	if result.Validate() != nil {
		t.Fatal("valid absent result refused")
	}
	snapshot := binding.RuntimeSnapshotV1{}
	result.Snapshot = &snapshot
	if result.Validate() == nil {
		t.Fatal("effect-absent carried a snapshot")
	}
	result.Classification = "effect-applied"
	result.ChangedAddresses = []string{"provision.node.a"}
	if result.Validate() != nil {
		t.Fatal("applied result refused")
	}
	result.ChangedAddresses = append(result.ChangedAddresses, "provision.node.a")
	if result.Validate() == nil {
		t.Fatal("duplicate changes accepted")
	}
	result.Classification = "success"
	if result.Validate() == nil {
		t.Fatal("open classification")
	}
}
