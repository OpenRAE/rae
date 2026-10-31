package urisafety

import (
	"errors"
	"testing"
)

// The expected verdicts are the output of the Python reference
// raes_contracts.uri_safety.validate_safe_absolute_uri, without options and
// with ForbiddenSchemes "data" and "FTP" and ForbidFragment.
func TestCheckMatchesThePythonReference(t *testing.T) {
	tests := []struct {
		uri           string
		plain, strict error
	}{
		{"https://example.org/a", nil, nil},
		{"http://example.org", nil, nil},
		{"https:", ErrNotAbsolute, ErrNotAbsolute},
		{"https:///path", ErrNotAbsolute, ErrNotAbsolute},
		{"http:/path", ErrNotAbsolute, ErrNotAbsolute},
		{"urn:isbn:0451450523", nil, nil},
		{"mailto:a@b.c", nil, nil},
		{"//example.org/a", ErrNotAbsolute, ErrNotAbsolute},
		{"/relative", ErrNotAbsolute, ErrNotAbsolute},
		{"relative", ErrNotAbsolute, ErrNotAbsolute},
		{"ftp://example.org/f", nil, ErrForbiddenScheme},
		{"https://user@example.org/", ErrCredentials, ErrCredentials},
		{"https://user:pw@example.org/", ErrCredentials, ErrCredentials},
		{"https://example.org/#frag", nil, ErrFragment},
		{"https://example.org/#", nil, nil},
		{"https://example.org/?token=1", ErrSecretQuery, ErrSecretQuery},
		{"https://example.org/?x=1&API_KEY=2", ErrSecretQuery, ErrSecretQuery},
		{"https://example.org/?my_secret_value=1", ErrSecretQuery, ErrSecretQuery},
		{"https://example.org/?\u017fecret=1", ErrSecretQuery, ErrSecretQuery},
		{"https://example.org/?pa\u00dfword=1", ErrSecretQuery, ErrSecretQuery},
		{"https://example.org/?to%6Ben=1", ErrSecretQuery, ErrSecretQuery},
		{"https://example.org/?to+ken=1", nil, nil},
		{"https://example.org/?x=1;token=2", nil, nil},
		{"https://example.org/?&&a=1", nil, nil},
		{"https://example.org/?=token", nil, nil},
		{"https://example.org/?tok%ZZen=1", nil, nil},
		{"https://example.org/?%E2%80%8Btoken=1", ErrSecretQuery, ErrSecretQuery},
		{"https://[::1]/a", nil, nil},
		{"https://[::1]:443/a", nil, nil},
		{"https://[1.2.3.4]/", ErrInvalid, ErrInvalid},
		{"https://[v1.fe80::a]/", nil, nil},
		{"https://[vz.x]/", ErrInvalid, ErrInvalid},
		{"https://[::1/", ErrInvalid, ErrInvalid},
		{"https://::1]/", ErrInvalid, ErrInvalid},
		{"https://a[::1]/", ErrInvalid, ErrInvalid},
		{"https://[::1]x/", ErrInvalid, ErrInvalid},
		{"https://[fe80::1%25eth0]/", nil, nil},
		{"https://ex\u2100ample.org/", ErrInvalid, ErrInvalid},
		{"https://ex\u00e4mple.org/", nil, nil},
		{"\u0000 https://example.org/", nil, nil},
		{"ht\ttps://example.org/", nil, nil},
		{"HTTPS://EXAMPLE.ORG/", nil, nil},
		{"1http://example.org/", ErrNotAbsolute, ErrNotAbsolute},
		{"h_t://example.org/", ErrNotAbsolute, ErrNotAbsolute},
		{"Secret-Key", ErrNotAbsolute, ErrNotAbsolute},
		{"data:,x", nil, ErrForbiddenScheme},
	}
	strict := Options{ForbiddenSchemes: []string{"data", "FTP"}, ForbidFragment: true}
	for _, test := range tests {
		if err := Check(test.uri, Options{}); !errors.Is(err, test.plain) || (err == nil) != (test.plain == nil) {
			t.Errorf("Check(%q) = %v, want %v", test.uri, err, test.plain)
		}
		if err := Check(test.uri, strict); !errors.Is(err, test.strict) || (err == nil) != (test.strict == nil) {
			t.Errorf("Check(%q, strict) = %v, want %v", test.uri, err, test.strict)
		}
	}
}

func TestUnquoteDecodesEachASCIIRun(t *testing.T) {
	tests := map[string]string{
		"plain":     "plain",
		"a%41b":     "aAb",
		"%e2%80%8b": "\u200b",
		"%ZZ%4":     "%ZZ%4",
		"%FFé%41":   "\ufffdéA",
		"é%C3%A9":   "éé",
	}
	for input, want := range tests {
		if got := unquote(input); got != want {
			t.Errorf("unquote(%q) = %q, want %q", input, got, want)
		}
	}
}

func FuzzCheckNeverPanics(f *testing.F) {
	f.Add("https://[::1]/?token=1#x")
	f.Add("\x00 HTTP://exämple.org/?%FF=1")
	f.Fuzz(func(_ *testing.T, uri string) {
		_ = Check(uri, Options{ForbiddenSchemes: []string{"data"}, ForbidFragment: true})
	})
}
