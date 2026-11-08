package governance

import "testing"

func TestJSONWorkerReference(t *testing.T) {
	for _, tc := range readReference[[]struct{ Value, Error string }](t, "worker-integer-reference") {
		t.Setenv("RAES_JSON_SCHEMA_WORKERS", tc.Value)
		err := jsonWorkerSetting()
		actual := ""
		if err != nil {
			actual = err.Error()
		}
		if actual != tc.Error {
			t.Errorf("workers %q: %q want %q", tc.Value, actual, tc.Error)
		}
	}
}
