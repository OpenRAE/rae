package digest

import (
	"strings"
	"testing"
)

func TestSHA256RendersThePrefixedLowercaseHexDigest(t *testing.T) {
	tests := map[string]string{
		"":    "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
		"abc": "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
	}
	for input, want := range tests {
		if got := SHA256([]byte(input)); got != want {
			t.Errorf("SHA256(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestPublishedDigestStringGrammar(t *testing.T) {
	for _, test := range []struct {
		name   string
		digits int
	}{{"sha256", 64}, {"sha384", 96}, {"sha512", 128}, {"blake3", 64}} {
		for _, ch := range []string{"0", "a", "F"} {
			if !Valid(test.name + ":" + strings.Repeat(ch, test.digits)) {
				t.Errorf("Valid(%s) = false, want true", test.name)
			}
		}
		for _, text := range []string{strings.Repeat("a", test.digits-1), strings.Repeat("a", test.digits+1), strings.Repeat("g", test.digits)} {
			if Valid(test.name + ":" + text) {
				t.Errorf("Valid(invalid %s) = true, want false", test.name)
			}
		}
	}
	for _, text := range []string{"", "sha256", "SHA256:" + strings.Repeat("0", 64), "md5:" + strings.Repeat("0", 32)} {
		if Valid(text) {
			t.Errorf("Valid(%q) = true, want false", text)
		}
	}
}
