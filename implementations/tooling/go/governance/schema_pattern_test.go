package governance

import "testing"

func TestSchemaPatternReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Profile, Pattern, Value string
		Matches                 bool
	}](t, "schema-pattern-reference") {
		re, err := compileSchemaPattern(tc.Pattern, tc.Profile == "python")
		if err != nil {
			t.Errorf("%s %q: %v", tc.Profile, tc.Pattern, err)
			continue
		}
		if got := re.MatchString(tc.Value); got != tc.Matches {
			t.Errorf("%s %q on %q=%t want %t", tc.Profile, tc.Pattern, tc.Value, got, tc.Matches)
		}
	}
}

func TestSchemaPatternUnsupported(t *testing.T) {
	for _, source := range []string{`(?=a)`, `(a)\1`, `(?m)a$`, `(?s).`, `\Qx\E`, `\p{L}`, `\x{61}`, `\uZZZZ`} {
		for _, python := range []bool{false, true} {
			if _, err := compileSchemaPattern(source, python); err == nil {
				t.Errorf("accepted unsupported %q python=%t", source, python)
			}
		}
	}
}
