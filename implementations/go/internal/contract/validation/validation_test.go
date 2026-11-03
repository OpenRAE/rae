package validation

import (
	"io/fs"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

func TestPublishedSchemaBoundary(t *testing.T) {
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"domain-profile-binding-v1", `{}`, false},
		{"sdl-authoring-input-v1", `{"name":"example"}`, true},
		{"sdl-authoring-input-v1", `{"name":"example","name":"other"}`, false},
		{"sdl-authoring-input-v1", `{"name":1}`, false},
		{"unknown-v1", `{}`, false},
	} {
		checkErr := v.CheckSchema(test.id, []byte(test.raw), ingress.Limits{MaxBytes: 1048576, MaxDepth: 64})
		if (checkErr == nil) != test.valid {
			t.Errorf("CheckSchema(%s,%s) = %v, want valid=%v", test.id, test.raw, checkErr, test.valid)
		}
	}
	value, err := v.Validate("sdl-authoring-input-v1", []byte(`{"name":"example"}`), ingress.Limits{MaxBytes: 1024, MaxDepth: 32}, nil)
	if err == nil {
		t.Errorf("Validate() = %v, want missing semantic rules", value)
	}
}

func TestRegexCompatibility(t *testing.T) {
	for _, test := range []struct {
		pattern, value string
		want           bool
	}{
		{`^a$`, "a\n", true}, {`^a$(?![\s\S])`, "a\n", false},
		{`^\d$`, "١", true}, {`^\s$`, "\u00a0", true},
		{`^[^\s]+$`, "a\u00a0b", false}, {`^[kK\u212a]$`, "K", true},
	} {
		r, err := compilePattern(test.pattern)
		if err != nil {
			t.Fatal(err)
		}
		if got := r.MatchString(test.value); got != test.want {
			t.Errorf("MatchString(%q,%q) = %v, want %v", test.pattern, test.value, got, test.want)
		}
	}
}

func TestBindingFixtureRoundTrips(t *testing.T) {
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ id, path string }{
		{"random-stream-profile-v1", "fixtures/profiles/random-stream-profile-v1/valid/blake3-xof-v1.json"},
		{"participant-execution-service-state-v1", "fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json"},
		{"operation-receipt-v1", "fixtures/control-plane/operation-receipt-v1/valid/accepted.json"},
		{"domain-profile-binding-v1", "fixtures/profiles/domain-profile-binding-v1/valid/reference.json"},
	} {
		data, readErr := fs.ReadFile(source, test.path)
		if readErr != nil {
			t.Fatal(readErr)
		}
		if _, decodeErr := v.DecodeSchema(test.id, data, ingress.Limits{MaxBytes: 4194304, MaxDepth: 64}); decodeErr != nil {
			t.Errorf("DecodeSchema(%s) = %v", test.id, decodeErr)
		}
	}
}

func TestRejectsUnsupportedPatterns(t *testing.T) {
	for _, text := range []string{`(?=a)`, `\u00`, `\uZZZZ`, `[\S]`, `[`} {
		if _, err := compilePattern(text); err == nil {
			t.Errorf("compilePattern(%q) = nil, want refusal", text)
		}
	}
	for _, text := range []string{`\D`, `\S`, `\.`} {
		if _, err := compilePattern(text); err != nil {
			t.Errorf("compilePattern(%q) = %v", text, err)
		}
	}
}
