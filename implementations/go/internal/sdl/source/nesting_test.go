package source

import (
	"fmt"
	"strings"
	"testing"
)

func TestBlockDepthCountsActiveAncestors(t *testing.T) {
	var siblings strings.Builder
	for i := range 300 {
		fmt.Fprintf(&siblings, "entry_%d:\n  nested:\n    value: text\n", i)
	}
	options := DefaultOptions()
	options.Limits.MaxDepth = 8
	for _, raw := range []string{siblings.String(), "root:\n" + strings.Repeat(" ", 200) + "leaf: text\n", "root: [\n    {leaf: text}\n]\n"} {
		if _, err := Decode([]byte(raw), options); err != nil {
			t.Fatalf("shallow source refused: %v", err)
		}
	}
	var nested strings.Builder
	for i := range 10 {
		fmt.Fprintf(&nested, "%sentry:\n", strings.Repeat(" ", i))
	}
	nested.WriteString("          value: text\n")
	for _, raw := range []string{nested.String(), strings.Repeat("- ", 10) + "text\n", strings.Repeat("[", 10) + "text" + strings.Repeat("]", 10)} {
		requireLimit(t, []byte(raw), options)
	}
}

func TestLiteralMappingKeysRejectVariableTokens(t *testing.T) {
	for _, key := range []string{"${name}", "prefix-${name}", "${demo.__private.name}"} {
		raw := []byte("labels: {'" + key + "': text}\n")
		_, err := Decode(raw, DefaultOptions())
		findings := Diagnostics(err)
		if len(findings) != 1 || findings[0].Code != identifierInvalidCode {
			t.Fatalf("variable mapping key findings = %+v", findings)
		}
	}
	for _, raw := range []string{"labels: {'${UPPER}': text}\n", "profile_value: {'${name}': text}\n"} {
		if _, err := Decode([]byte(raw), DefaultOptions()); err != nil {
			t.Fatalf("literal or opaque-data key refused: %v", err)
		}
	}
}
