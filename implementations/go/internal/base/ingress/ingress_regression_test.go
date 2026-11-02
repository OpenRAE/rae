package ingress

import (
	"errors"
	"strings"
	"testing"
)

func TestRegressionRejectsUnknownRoot(t *testing.T) {
	for _, root := range []Root{0, -1, 99} {
		for _, data := range []string{"42", "{}", "[]", ""} {
			value, err := Parse([]byte(data), Limits{MaxBytes: 10}, root)
			failure, ok := errors.AsType[*Error](err)
			if value != nil || !ok || failure.Code != InvalidRoot {
				t.Errorf("Parse(%q, root=%d) = %v, %v, want nil, invalid-root", data, root, value, err)
			}
		}
	}
}

func TestRegressionExplicitDepthCannotRaiseDecoderCeiling(t *testing.T) {
	data := strings.Repeat("[", decoderDepth+1) + strings.Repeat("]", decoderDepth+1)
	_, err := Parse([]byte(data), Limits{MaxBytes: len(data), MaxDepth: decoderDepth + 10}, Array)
	failure, ok := errors.AsType[*Error](err)
	if !ok || failure.Code != TooDeep {
		t.Errorf("Parse(deep, explicit limit) = %v, want %s", err, TooDeep)
	}
}
