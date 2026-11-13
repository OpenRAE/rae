package admission

import (
	"encoding/json"
	"strconv"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func preparedSnapshotWithMetadata(t *testing.T, metadata any) binding.RuntimeSnapshotV1 {
	t.Helper()
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal(projectionTestJSON(t, map[string]any{"schema_version": "runtime-snapshot/v1", "entries": map[string]any{}, "metadata": metadata}), &snapshot) != nil {
		t.Fatal("snapshot fixture")
	}
	return snapshot
}

func TestPreparedSnapshotUsesRuntimeAggregateAndOrdinaryTextLimits(t *testing.T) {
	for _, width := range []int{200, 400} {
		metadata := map[string]any{}
		for i := range 200 {
			metadata[strconv.Itoa(i)] = make([]any, width)
		}
		err := CheckPreparedSnapshot(preparedSnapshotWithMetadata(t, metadata))
		if (err == nil) != (width == 200) {
			t.Fatalf("runtime aggregate width%d err=%v", width, err)
		}
	}
	for _, key := range []string{"ordinary", "attestation_sdl", "snapshot"} {
		if CheckPreparedSnapshot(preparedSnapshotWithMetadata(t, map[string]any{key: strings.Repeat("x", (1<<20)+1)})) == nil {
			t.Fatalf("arbitrary %s gained a document scalar allowance", key)
		}
	}
}
