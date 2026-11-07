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

func TestSchemaPythonUnicodeVersion(t *testing.T) {
	for _, tc := range []struct {
		pattern, value string
		matches        bool
	}{
		{`^\d$`, "٢", true},
		{`^\d$`, "\U00011de2", false},
		{`^\w$`, "\U0001e6c0", false},
		{`^\D$`, "\U00011de2", true},
	} {
		re, err := compileSchemaPattern(tc.pattern, true)
		if err != nil {
			t.Fatal(err)
		}
		if got := re.MatchString(tc.value); got != tc.matches {
			t.Errorf("%q on %q=%t want=%t", tc.pattern, tc.value, got, tc.matches)
		}
	}
}
