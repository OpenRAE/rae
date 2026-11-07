package governance

import (
	"net/url"
	"strings"

	"golang.org/x/text/unicode/norm"
)

// CheckDocumentationURL checks a raw or CSV directive URL before the trusted
// builder opens it. A refusal must mark the page for rereading on later builds.
// This function performs no I/O and grants no filesystem or network authority.
func CheckDocumentationURL(value string) error {
	value = strings.TrimFunc(value, pythonWhitespace)
	if strings.HasPrefix(value, "<") && strings.HasSuffix(value, ">") {
		value = strings.TrimFunc(value[1:len(value)-1], pythonWhitespace)
	}
	if strings.HasPrefix(value, "URL:") {
		value = strings.TrimFunc(value[4:], pythonWhitespace)
	}
	value = strings.TrimLeftFunc(value, func(r rune) bool { return r <= 0x20 })
	value = strings.NewReplacer("\r", "", "\n", "", "\t", "").Replace(value)
	parsed, err := url.Parse(value)
	if err != nil {
		return policyInputError("has a :url: that urllib cannot parse")
	}
	authority := strings.NewReplacer("@", "", ":", "", "#", "", "?", "").Replace(parsed.Host)
	if normalized := norm.NFKC.String(authority); normalized != authority && strings.ContainsAny(normalized, "/?#@:") {
		return policyInputError("has a :url: that urllib cannot parse")
	}
	if strings.EqualFold(parsed.Scheme, "file") {
		return policyInputError("must not read a local file through a file: URL")
	}
	return nil
}
