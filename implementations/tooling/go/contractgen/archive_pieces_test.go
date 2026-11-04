package contractgen

import (
	"bytes"
	"encoding/hex"
	"fmt"
	"strconv"
	"strings"
	"testing"
)

func TestArchivePiecesPreserveBytesAtEveryBoundary(t *testing.T) {
	for _, size := range []int{0, 1, 131071, 131072, 131073, 262144, 262145} {
		t.Run(strconv.Itoa(size), func(t *testing.T) { checkArchiveBoundary(t, size) })
	}
}

func checkArchiveBoundary(t *testing.T, size int) {
	t.Helper()
	original := make([]byte, size)
	for index := range original {
		original[index] = byte(index % 251)
	}
	output := map[string][]byte{"retained": []byte("binding")}
	addArchivePieces(output, original)
	count := (size + 131071) / 131072
	if len(output) != count+1 || string(output["retained"]) != "binding" {
		t.Fatal("incorrect archive inventory or overwritten output")
	}
	var actual bytes.Buffer
	for index := range count {
		name := fmt.Sprintf("%scorpus/data/%04d", outputRoot, index)
		encoded, exists := output[name]
		if !exists {
			t.Fatal("missing archive piece", name)
		}
		actual.Write(decodeArchiveBoundary(t, encoded))
	}
	if !bytes.Equal(actual.Bytes(), original) {
		t.Fatal("archive split changed original bytes")
	}
}

func decodeArchiveBoundary(t *testing.T, encoded []byte) []byte {
	t.Helper()
	if len(encoded) <= 1 || len(encoded) > 262145 || encoded[len(encoded)-1] != '\n' {
		t.Fatal("empty or oversized archive piece")
	}
	decoded, err := hex.DecodeString(strings.TrimSuffix(string(encoded), "\n"))
	if err != nil {
		t.Fatal(err)
	}
	return decoded
}
