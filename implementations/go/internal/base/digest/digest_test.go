package digest

import "testing"

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
