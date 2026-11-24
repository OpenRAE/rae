// Package urisafety checks that an absolute URI is inert and carries no
// secret, without dereferencing it (Go port 06, issue #1779).
//
// The check splits a URI as Python's urllib.parse.urlsplit does and reads its
// query as urllib.parse.parse_qsl does, so that the Go and the Python
// implementations accept the same URIs. net/url follows other rules.
package urisafety

import (
	"net/netip"
	"regexp"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"

	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"
)

// The reasons that Check refuses a URI.
var (
	ErrInvalid         = fault.New(fault.InvalidInput, "uri-invalid", nil)
	ErrNotAbsolute     = fault.New(fault.InvalidInput, "uri-absolute", nil)
	ErrForbiddenScheme = fault.New(fault.InvalidInput, "uri-scheme", nil)
	ErrCredentials     = fault.New(fault.InvalidInput, "uri-credentials", nil)
	ErrFragment        = fault.New(fault.InvalidInput, "uri-fragment", nil)
	ErrSecretQuery     = fault.New(fault.InvalidInput, "uri-secret", nil)
)

// ipvFuture matches an IPvFuture literal inside brackets.
var ipvFuture = regexp.MustCompile(`^v[a-fA-F0-9]+\..+$`)

// The characters that start a scheme and the characters of a scheme, as
// urlsplit accepts them.
const (
	asciiLetters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
	schemeChars  = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+-."
)

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
	if scheme, rest, found := strings.Cut(uri, ":"); found && scheme != "" &&
		strings.ContainsRune(asciiLetters, rune(scheme[0])) && strings.Trim(scheme, schemeChars) == "" {
		parts.scheme, uri = strings.ToLower(scheme), rest
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
	// Python's ipaddress also refuses a zone that contains a percent sign.
	address, err := netip.ParseAddr(host)
	if err != nil || address.Is4() || strings.Contains(address.Zone(), "%") {
		return ErrInvalid
	}
	return nil
}

// checkNormalizedNetloc refuses a netloc whose NFKC form contains a delimiter
// that the original text does not, as urlsplit does. The netloc holds no
// slash, question mark, or number sign, and the check removes the at signs and
// colons first, so each delimiter in the result comes from the normalization.
func checkNormalizedNetloc(netloc string) error {
	stripped := strings.NewReplacer("@", "", ":", "").Replace(netloc)
	if strings.ContainsAny(norm.NFKC.String(stripped), "/?#@:") {
		return ErrInvalid
	}
	return nil
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

// unquote decodes each %XX escape of s and replaces each run of invalid UTF-8
// with U+FFFD. An invalid escape stays as it is. Python's unquote decodes each
// ASCII run alone and replaces each invalid sequence. Decoded bytes cannot join
// the multibyte text after them, because such text starts with a lead byte. So
// the two decodings differ only in the number of replacement characters. The
// field-name check gives the same verdict for both, because each secret name
// and word is ASCII.
func unquote(s string) string {
	var out []byte
	for i := 0; i < len(s); i++ {
		if s[i] == '%' && i+2 < len(s) {
			// ParseUint takes only hexadecimal digits: no sign and no underscore.
			if b, err := strconv.ParseUint(s[i+1:i+3], 16, 8); err == nil {
				out = append(out, byte(b))
				i += 2
				continue
			}
		}
		out = append(out, s[i])
	}
	return strings.ToValidUTF8(string(out), "\uFFFD")
}
