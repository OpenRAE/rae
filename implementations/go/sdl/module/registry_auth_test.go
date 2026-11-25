package module

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func TestAnonymousBearerChallengeRetriesOnceWithACachedToken(t *testing.T) {
	var tokens atomic.Int64
	authority := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tokens.Add(1)
		if r.URL.Query().Get("service") != "registry" || strings.Join(r.URL.Query()["scope"], " ") != "repository:a:pull extra" {
			t.Errorf("token request = %s", r.URL.RawQuery)
		}
		_, _ = w.Write([]byte(`{"token":"","access_token":"abc.def"}`))
	}))
	defer authority.Close()
	registry := httptest.NewTLSServer(challengingRegistry(t, authority.URL))
	defer registry.Close()
	client := registry.Client()
	client.CheckRedirect = func(request *http.Request, _ []*http.Request) error {
		request.Header.Del("Authorization")
		return nil
	}
	fetcher := testFetcher(client)
	for range 2 {
		if raw, err := fetcher.fetch(t.Context(), registry.URL+"/manifest", 10); err != nil || string(raw) != "x" {
			t.Fatalf("challenged fetch = %q, %v", raw, err)
		}
	}
	if raw, err := fetcher.fetch(t.Context(), registry.URL+"/redirect", 10); err != nil || string(raw) != "y" {
		t.Fatalf("redirected fetch = %q, %v", raw, err)
	}
	if tokens.Load() != 1 {
		t.Fatalf("token requests = %d; want one cached token", tokens.Load())
	}
}

// challengingRegistry answers with a Bearer challenge until a request carries
// the token, and redirects a token-bearing request to check header stripping.
func challengingRegistry(t *testing.T, realm string) http.Handler {
	t.Helper()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/redirect" && r.Header.Get("Authorization") != "":
			http.Redirect(w, r, "/landing", http.StatusTemporaryRedirect)
		case r.URL.Path == "/landing":
			if r.Header.Get("Authorization") != "" {
				t.Error("a redirect carried the challenge token")
			}
			_, _ = w.Write([]byte("y"))
		case r.Header.Get("Authorization") == "Bearer abc.def":
			_, _ = w.Write([]byte("x"))
		default:
			w.Header().Set("WWW-Authenticate", `Bearer realm="`+realm+`/token",service="registry",scope="repository:a:pull extra"`)
			w.WriteHeader(http.StatusUnauthorized)
		}
	})
}

func TestBearerChallengeGrammarAndRealmAreStrict(t *testing.T) {
	for _, test := range []struct {
		header string
		valid  bool
	}{
		{`Bearer realm="https://auth.example/token",service="r",scope="repository:a:pull"`, true},
		{`bearer realm=token-realm`, true}, {`Bearer realm=https://auth.example/token`, false},
		{`Bearer realm="https://auth.example/token",realm="https://other.example"`, false},
		{`Bearer service="r"`, false},
		{`Bearer realm="https://auth.example/token",,service="r"`, false},
		{`Bearer realm="https://auth.example/token",scope="bad\"scope"`, false},
	} {
		if _, err := parseBearerChallenge(test.header); (err == nil) != test.valid {
			t.Errorf("parse(%s) = %v; want valid=%t", test.header, err, test.valid)
		}
	}
	for _, test := range []struct {
		realm string
		valid bool
	}{
		{"https://auth.example/token", true}, {"http://auth.example/token", false}, {"https://user@auth.example/token", false},
		{"https://auth%2eexample/token", false}, {"https://auth.example/token#part", false}, {"https://auth..example/token", false},
		{"https://auth.example:0/token", false}, {"https://auth.example/to ken", false},
	} {
		if httpsURL(test.realm) != test.valid {
			t.Errorf("httpsURL(%s) != %t", test.realm, test.valid)
		}
	}
}

func TestTokenResponseRequiresABearerTokenWithoutRedirect(t *testing.T) {
	for _, body := range []string{`{"token":"has space"}`, `{"token":7}`, `[]`, `{}`} {
		authority := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(body)) }))
		fetcher := testFetcher(authority.Client())
		if _, err := fetcher.token(t.Context(), bearerChallenge{realm: authority.URL}); err == nil {
			t.Errorf("token response %s accepted", body)
		}
		authority.Close()
	}
	moved := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/elsewhere", http.StatusFound)
	}))
	defer moved.Close()
	if _, err := testFetcher(moved.Client()).token(t.Context(), bearerChallenge{realm: moved.URL}); err == nil {
		t.Fatal("token request followed a redirect")
	}
}

func TestChallengeComesFromTheRequestedURLWithOneValidBearer(t *testing.T) {
	const address = "https://registry.example/v2/a/manifests/1"
	request, err := http.NewRequestWithContext(t.Context(), http.MethodGet, address, nil)
	if err != nil {
		t.Fatal(err)
	}
	valid := `Bearer realm="https://auth.example/token?x=1",service="r",scope="repository:a:pull"`
	for name, test := range map[string]struct {
		headers           []string
		address           string
		request           *http.Request
		challenged, valid bool
	}{
		"bearer":         {[]string{`Basic realm="r"`, valid}, address, request, true, true},
		"other address":  {[]string{valid}, address + "?redirected", request, false, true},
		"no request":     {[]string{valid}, address, nil, false, true},
		"no bearer":      {[]string{`Basic realm="r"`}, address, request, false, true},
		"two bearers":    {[]string{valid, valid}, address, request, false, false},
		"malformed":      {[]string{`Bearer realm=`}, address, request, false, false},
		"insecure realm": {[]string{`Bearer realm="http://auth.example/token"`}, address, request, false, false},
	} {
		response := &http.Response{Request: test.request, Header: http.Header{"Www-Authenticate": test.headers}, Body: http.NoBody}
		challenge, challenged, err := challengeFor(response, test.address)
		_ = response.Body.Close()
		if challenged != test.challenged || (err == nil) != test.valid {
			t.Errorf("%s: challenge = %t, %v", name, challenged, err)
		}
		if name == "bearer" {
			if got, err := challenge.tokenURL(); err != nil || got != "https://auth.example/token?x=1&service=r&scope=repository%3Aa%3Apull" {
				t.Errorf("token URL = %q, %v", got, err)
			}
		}
	}
	if _, err := (bearerChallenge{realm: "https://auth.example/%zz"}).tokenURL(); err == nil {
		t.Error("an unparsable realm produced a token URL")
	}
}

func TestTokenFieldUsesTheReferenceTruthRule(t *testing.T) {
	for value, want := range map[any]bool{nil: false, "": false, "a": true, false: false, true: true, float64(0): false, float64(2): true} {
		if truthy(value) != want {
			t.Errorf("truthy(%#v) != %t", value, want)
		}
	}
	if truthy(map[string]any{}) || !truthy(map[string]any{"a": 1}) || truthy([]any{}) || !truthy([]any{1}) || !truthy(struct{}{}) {
		t.Error("container truth differs from the reference rule")
	}
}
