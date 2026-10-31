// Package urisafety checks that an absolute URI is inert and carries no
// secret, without dereferencing it (Go port 06, issue #1779).
//
// The check splits a URI as Python's urllib.parse.urlsplit does and reads its
// query as urllib.parse.parse_qsl does, so that the Go and the Python
// implementations accept the same URIs. net/url follows other rules.
package urisafety

import (
	"errors"
	"net/netip"
	"regexp"
	"strings"

	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"
)

// The reasons that Check refuses a URI.
var (
	ErrInvalid         = errors.New("urisafety: the URI is invalid")
	ErrNotAbsolute     = errors.New("urisafety: the URI is not absolute")
	ErrForbiddenScheme = errors.New("urisafety: the URI uses a forbidden scheme")
	ErrCredentials     = errors.New("urisafety: the URI contains credential userinfo")
	ErrFragment        = errors.New("urisafety: the URI contains a fragment")
	ErrSecretQuery     = errors.New("urisafety: the URI contains a secret-bearing query field")
)

// ipvFuture matches an IPvFuture literal inside brackets.
var ipvFuture = regexp.MustCompile(`^v[a-fA-F0-9]+\..+$`)

// Options select the optional checks of Check.
type Options struct {
	ForbiddenSchemes []string
	ForbidFragment   bool
}

// Check refuses a relative URI, a forbidden scheme, credential userinfo, a
// fragment when opts forbids one, and a query field whose name looks like a
// secret.
func Check(uri string, opts Options) error {
	parts, err := split(uri)
	if err != nil {
		return err
	}
	fold := cases.Fold()
	scheme := fold.String(parts.scheme)
	if scheme == "" || (scheme == "http" || scheme == "https") && parts.netloc == "" {
		return ErrNotAbsolute
	}
	for _, forbidden := range opts.ForbiddenSchemes {
		if scheme == fold.String(forbidden) {
			return ErrForbiddenScheme
		}
	}
	if strings.Contains(parts.netloc, "@") {
		return ErrCredentials
	}
	if opts.ForbidFragment && parts.fragment != "" {
		return ErrFragment
	}
	if hasSecretField(parts.query, fold) {
		return ErrSecretQuery
	}
	return nil
}

type uriParts struct {
	scheme, netloc, query, fragment string
}

// split splits uri into its components as Python's urlsplit does.
func split(uri string) (uriParts, error) {
	uri = strings.TrimLeft(uri, "\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f"+
		"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f ")
	uri = strings.NewReplacer("\t", "", "\r", "", "\n", "").Replace(uri)
	var parts uriParts
	if i := strings.IndexByte(uri, ':'); i > 0 && isASCIILetter(uri[0]) &&
		strings.Trim(uri[:i], "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+-.") == "" {
		parts.scheme, uri = strings.ToLower(uri[:i]), uri[i+1:]
	}
	if strings.HasPrefix(uri, "//") {
		end := len(uri)
		if i := strings.IndexAny(uri[2:], "/?#"); i >= 0 {
			end = i + 2
		}
		parts.netloc, uri = uri[2:end], uri[end:]
		if err := checkBrackets(parts.netloc); err != nil {
			return uriParts{}, err
		}
	}
	uri, parts.fragment, _ = strings.Cut(uri, "#")
	_, parts.query, _ = strings.Cut(uri, "?")
	if err := checkNormalizedNetloc(parts.netloc); err != nil {
		return uriParts{}, err
	}
	return parts, nil
}

func isASCIILetter(c byte) bool {
	return 'a' <= c && c <= 'z' || 'A' <= c && c <= 'Z'
}

// checkBrackets refuses an unbalanced bracket and a bracketed host that is
// not an IPv6 or IPvFuture literal.
func checkBrackets(netloc string) error {
	open, closing := strings.Contains(netloc, "["), strings.Contains(netloc, "]")
	if open != closing {
		return ErrInvalid
	}
	if !open {
		return nil
	}
	hostAndPort := netloc[strings.LastIndexByte(netloc, '@')+1:]
	before, bracketed, hasBracket := strings.Cut(hostAndPort, "[")
	host, _, _ := strings.Cut(hostAndPort, ":")
	if hasBracket {
		if before != "" {
			return ErrInvalid
		}
		var port string
		host, port, _ = strings.Cut(bracketed, "]")
		if port != "" && !strings.HasPrefix(port, ":") {
			return ErrInvalid
		}
	}
	if strings.HasPrefix(host, "v") {
		if !ipvFuture.MatchString(host) {
			return ErrInvalid
		}
		return nil
	}
	address, err := netip.ParseAddr(host)
	if err != nil || address.Is4() {
		return ErrInvalid
	}
	return nil
}

// checkNormalizedNetloc refuses a non-ASCII netloc whose NFKC form contains a
// delimiter that the original text does not.
func checkNormalizedNetloc(netloc string) error {
	if isASCII(netloc) {
		return nil
	}
	stripped := strings.NewReplacer("@", "", ":", "", "#", "", "?", "").Replace(netloc)
	normalized := norm.NFKC.String(stripped)
	if normalized != stripped && strings.ContainsAny(normalized, "/?#@:") {
		return ErrInvalid
	}
	return nil
}

func isASCII(s string) bool {
	for i := range len(s) {
		if s[i] >= 0x80 {
			return false
		}
	}
	return true
}

// hasSecretField reports whether a query field name, decoded and case-folded
// as parse_qsl and str.casefold do, names a secret or contains a secret word.
func hasSecretField(query string, fold cases.Caser) bool {
	for field := range strings.SplitSeq(query, "&") {
		if field == "" {
			continue
		}
		name, _, _ := strings.Cut(field, "=")
		if secretName(fold.String(unquote(strings.ReplaceAll(name, "+", " ")))) {
			return true
		}
	}
	return false
}

func secretName(name string) bool {
	switch name {
	case "access_token", "api_key", "apikey", "auth", "credential", "key", "password", "secret", "sig",
		"signature", "token":
		return true
	}
	for _, word := range []string{"api-key", "api_key", "apikey", "credential", "password", "secret", "signature", "token"} {
		if strings.Contains(name, word) {
			return true
		}
	}
	return false
}

// unquote decodes the percent escapes of each ASCII run of s as UTF-8, as
// Python's urllib.parse.unquote does. An invalid escape stays as it is, and an
// invalid UTF-8 sequence becomes U+FFFD.
func unquote(s string) string {
	if !strings.Contains(s, "%") {
		return s
	}
	var out strings.Builder
	for s != "" {
		end := strings.IndexFunc(s, func(r rune) bool { return r >= 0x80 })
		if end < 0 {
			end = len(s)
		}
		out.WriteString(strings.ToValidUTF8(decodePercents(s[:end]), "�"))
		s = s[end:]
		next := strings.IndexFunc(s, func(r rune) bool { return r < 0x80 })
		if next < 0 {
			next = len(s)
		}
		out.WriteString(s[:next])
		s = s[next:]
	}
	return out.String()
}

// decodePercents replaces each %XX escape of an ASCII string with its byte.
func decodePercents(s string) string {
	var out []byte
	for i := 0; i < len(s); i++ {
		if s[i] == '%' && i+2 < len(s) && isHex(s[i+1]) && isHex(s[i+2]) {
			out = append(out, unhex(s[i+1])<<4|unhex(s[i+2]))
			i += 2
			continue
		}
		out = append(out, s[i])
	}
	return string(out)
}

func isHex(c byte) bool {
	return '0' <= c && c <= '9' || 'a' <= c && c <= 'f' || 'A' <= c && c <= 'F'
}

func unhex(c byte) byte {
	if c <= '9' {
		return c - '0'
	}
	return c&^0x20 - 'A' + 10
}
