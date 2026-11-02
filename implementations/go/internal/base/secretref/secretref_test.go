package secretref

import (
	"errors"
	"strings"
	"testing"
)

func TestIdentityGrammarAndLengthBoundaries(t *testing.T) {
	for _, id := range []string{"a", "a0", "vault.production-key_1", strings.Repeat("a", 256)} {
		if !Valid(id) || Validate(id) != nil {
			t.Errorf("Validate(%q) refused a valid logical identity", id)
		}
	}
	for _, id := range []string{"", "A", "1a", "é", "a.", "a..b", "a-_b", "a/b", "a\n", strings.Repeat("a", 257)} {
		if Valid(id) || !errors.Is(Validate(id), ErrID) {
			t.Errorf("Validate(%q) accepted an invalid logical identity", id)
		}
	}
}
