package runtime_test

import (
	"bytes"
	"testing"

	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

func TestMaterializationSubmissionBoundsAndOwnsSDL(t *testing.T) {
	source := []byte("name: sample\n")
	result, err := runtimecontract.NewMaterializationSubmission(source)
	if err != nil {
		t.Fatal(err)
	}
	if result.ContractID != "backend-materialization-attestation-v1" {
		t.Fatal("incorrect contract")
	}
	source[0] = 'X'
	if !bytes.Equal(result.SDL, []byte("name: sample\n")) {
		t.Fatal("source alias retained")
	}
	if _, err := runtimecontract.NewMaterializationSubmission(bytes.Repeat([]byte("x"), 4<<20)); err != nil {
		t.Fatal("boundary rejected", err)
	}
	for _, data := range [][]byte{nil, {}, {0xff}, bytes.Repeat([]byte("x"), (4<<20)+1)} {
		if _, err := runtimecontract.NewMaterializationSubmission(data); err == nil {
			t.Fatal("invalid source accepted")
		}
	}
}
