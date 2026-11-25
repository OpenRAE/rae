package module

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"strings"
)

// Public registries answer an anonymous request with 401 and a Bearer
// challenge. The client requests an anonymous token from the challenge realm
// with its service and scope, then repeats the request with the token. No
// credential is read, stored or sent, and the token request follows no redirect.

// RFC 9110 token and quoted-string, restricted to ASCII; RFC 6749 scope-token;
// RFC 6750 b64token, the bearer credential syntax.
var (
	bearerScheme   = regexp.MustCompile(`^([!#$%&'*+.^_` + "`" + `|~0-9A-Za-z-]+)(?: +|$)`)
	bearerParam    = regexp.MustCompile(`^([!#$%&'*+.^_` + "`" + `|~0-9A-Za-z-]+)[ \t]*=[ \t]*([!#$%&'*+.^_` + "`" + `|~0-9A-Za-z-]+|"(?:[\t \x21\x23-\x5b\x5d-\x7e]|\\[\t \x21-\x7e])*")`)
	listSeparator  = regexp.MustCompile(`^[ \t]*,[ \t]*`)
	quotedPair     = regexp.MustCompile(`\\(.)`)
	scopeToken     = regexp.MustCompile(`^[\x21\x23-\x5b\x5d-\x7e]+$`)
	bearerToken    = regexp.MustCompile(`^[A-Za-z0-9._~+/-]+=*$`)
	visibleURLText = regexp.MustCompile(`^[\x21-\x7e]+$`)
)

// bearerChallenge holds the parameters of a token request; it is also the token cache key.
type bearerChallenge struct {
	realm, service, scope string
	hasService, hasScope  bool
}

// registryFetcher holds the client and the anonymous tokens of one import resolution.
type registryFetcher struct {
	client        *http.Client
	tokens        map[bearerChallenge]string
	metadataBytes int64
}

// tokenURL returns the realm with the service and each space-delimited scope entry as query parameters.
func (c bearerChallenge) tokenURL() (string, error) {
	parts, err := url.Parse(c.realm)
	if err != nil {
		return "", invalid()
	}
	query := []string{}
	if c.hasService {
		query = append(query, "service="+url.QueryEscape(c.service))
	}
	if c.hasScope {
		for entry := range strings.SplitSeq(c.scope, " ") {
			query = append(query, "scope="+url.QueryEscape(entry))
		}
	}
	joined := []string{}
	if parts.RawQuery != "" {
		joined = append(joined, parts.RawQuery)
	}
	if len(query) > 0 {
		joined = append(joined, strings.Join(query, "&"))
	}
	parts.RawQuery, parts.Fragment = strings.Join(joined, "&"), ""
	return parts.String(), nil
}

// challengeFor returns the Bearer challenge of a 401 from the requested URL itself.
func challengeFor(response *http.Response, address string) (bearerChallenge, bool, error) {
	if response.Request == nil || response.Request.URL.String() != address {
		return bearerChallenge{}, false, nil
	}
	bearer := []string{}
	for _, value := range response.Header.Values("WWW-Authenticate") {
		if isBearer(value) {
			bearer = append(bearer, value)
		}
	}
	if len(bearer) == 0 {
		return bearerChallenge{}, false, nil
	}
	if len(bearer) > 1 {
		return bearerChallenge{}, false, invalid()
	}
	challenge, err := parseBearerChallenge(bearer[0])
	if err != nil {
		return bearerChallenge{}, false, err
	}
	if !httpsURL(challenge.realm) {
		return bearerChallenge{}, false, invalid()
	}
	return challenge, true, nil
}

func isBearer(value string) bool {
	scheme := bearerScheme.FindStringSubmatch(strings.Trim(value, " \t"))
	return scheme != nil && strings.EqualFold(scheme[1], "bearer")
}

// parseBearerChallenge parses one Bearer challenge strictly. The realm is
// required, other parameters are ignored, and a duplicate parameter fails.
func parseBearerChallenge(value string) (bearerChallenge, error) {
	text := strings.Trim(value, " \t")
	scheme := bearerScheme.FindStringSubmatchIndex(text)
	if scheme == nil || !strings.EqualFold(text[scheme[2]:scheme[3]], "bearer") {
		return bearerChallenge{}, invalid()
	}
	params, err := authParams(text[scheme[1]:])
	if err != nil {
		return bearerChallenge{}, err
	}
	realm, hasRealm := params["realm"]
	scope, hasScope := params["scope"]
	if !hasRealm {
		return bearerChallenge{}, invalid()
	}
	if hasScope {
		for entry := range strings.SplitSeq(scope, " ") {
			if !scopeToken.MatchString(entry) {
				return bearerChallenge{}, invalid()
			}
		}
	}
	service, hasService := params["service"]
	return bearerChallenge{realm: realm, service: service, scope: scope, hasService: hasService, hasScope: hasScope}, nil
}

// authParams returns the comma-separated auth-params to the end of the text.
func authParams(text string) (map[string]string, error) {
	params := map[string]string{}
	for {
		match := bearerParam.FindStringSubmatch(text)
		if match == nil {
			return nil, invalid()
		}
		name := strings.ToLower(match[1])
		if _, duplicate := params[name]; duplicate {
			return nil, invalid()
		}
		params[name] = unquoted(match[2])
		text = text[len(match[0]):]
		if text == "" {
			return params, nil
		}
		separator := listSeparator.FindString(text)
		if separator == "" {
			return nil, invalid()
		}
		text = text[len(separator):]
	}
}

func unquoted(value string) string {
	if !strings.HasPrefix(value, `"`) {
		return value
	}
	return quotedPair.ReplaceAllString(value[1:len(value)-1], "$1")
}

// httpsURL accepts only an absolute https URL with a host and no userinfo,
// percent-encoded authority, fragment or whitespace.
func httpsURL(raw string) bool {
	if !visibleURLText.MatchString(raw) {
		return false
	}
	parts, err := url.Parse(raw)
	if err != nil || parts.Scheme != schemeHTTPS || parts.Fragment != "" || strings.Contains(raw, "#") || parts.User != nil || strings.Contains(parts.Host, "%") {
		return false
	}
	if port := parts.Port(); port == "0" {
		return false
	}
	return asciiHost(parts.Hostname())
}

// asciiHost applies the IDNA label rules to an ASCII host: no empty or overlong label.
func asciiHost(host string) bool {
	if host == "" || len(host) > 253 {
		return false
	}
	for label := range strings.SplitSeq(strings.TrimSuffix(host, "."), ".") {
		if label == "" || len(label) > 63 {
			return false
		}
	}
	return true
}

// token returns the cached anonymous token of a challenge, or requests one.
func (f *registryFetcher) token(ctx context.Context, challenge bearerChallenge) (string, error) {
	if token, cached := f.tokens[challenge]; cached {
		return token, nil
	}
	address, err := challenge.tokenURL()
	if err != nil {
		return "", err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return "", invalid()
	}
	request.Header.Set("Accept", "application/json")
	// The validated HTTPS realm is the only hop: no redirect is followed.
	client := &http.Client{Transport: f.client.Transport, Timeout: f.client.Timeout, CheckRedirect: func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}}
	response, err := client.Do(request)
	if err != nil {
		return "", operational(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return "", operational(errors.New("anonymous registry token refused"))
	}
	raw, err := readBounded(response, f.metadataBytes)
	if err != nil {
		return "", err
	}
	var document map[string]any
	if json.Unmarshal(raw, &document) != nil || document == nil {
		return "", invalid()
	}
	token := document["token"]
	if !truthy(token) {
		token = document["access_token"]
	}
	text, ok := token.(string)
	if !ok || !bearerToken.MatchString(text) {
		return "", invalid()
	}
	f.tokens[challenge] = text
	return text, nil
}

// truthy applies the reference truth rule to a decoded JSON value.
func truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case string:
		return typed != ""
	case bool:
		return typed
	case float64:
		return typed != 0
	case map[string]any:
		return len(typed) > 0
	case []any:
		return len(typed) > 0
	default:
		return true
	}
}
