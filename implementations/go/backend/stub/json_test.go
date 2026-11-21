package stub_test

import (
	"encoding/json"
	"testing"
)

func marshalTest(t *testing.T, input any) []byte {
	t.Helper()
	raw, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
