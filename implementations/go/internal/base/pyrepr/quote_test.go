package pyrepr

import "testing"

func TestQuotePreservesReferenceUnicodeVersionAndEscapes(t *testing.T) {
	for input, want := range map[string]string{
		"a'b": `"a'b"`, "a\"b": `'a"b'`, "'\"\\\t\r\n": `'\'"\\\t\r\n'`,
		"\x00\b\f\v\a":       `'\x00\x08\x0c\x0b\x07'`,
		"\u00a0\u200b\u2028": `'\xa0\u200b\u2028'`,
		"\U0001fae9":         "'\U0001fae9'", // Unicode16 face with bags under eyes.
		"\U0001faea":         `'\U0001faea'`, // Unicode17 distorted face stays unassigned in reference.
	} {
		if got := Quote(input); got != want {
			t.Errorf("quote %q: got %q want %q", input, got, want)
		}
	}
}
