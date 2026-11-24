package governance

import (
	"net/url"
	"slices"
	"strings"

	"golang.org/x/text/unicode/norm"
)

func secretArtifactLocator(locator string) bool {
	if strings.Contains(locator, "${") || strings.Contains(locator, "{{") {
		return true
	}
	locator = strings.TrimLeftFunc(locator, func(r rune) bool { return r <= 0x20 })
	locator = strings.NewReplacer("\r", "", "\n", "", "\t", "").Replace(locator)
	parsed, err := url.Parse(locator)
	if err != nil || parsed.User != nil {
		return true
	}
	// urllib rejects authority characters whose NFKC form introduces delimiters.
	authority := strings.NewReplacer("@", "", ":", "", "#", "", "?", "").Replace(parsed.Host)
	if normalized := norm.NFKC.String(authority); normalized != authority && strings.ContainsAny(normalized, "/?#@:") {
		return true
	}
	for entry := range strings.SplitSeq(parsed.RawQuery, "&") {
		key, _, _ := strings.Cut(entry, "=")
		decoded, err := url.QueryUnescape(key)
		if err == nil {
			key = decoded
		}
		if slices.Contains([]string{"access_token", "apikey", "api_key", "auth", "key", "password", "secret", "sig", "signature", "token"}, strings.ToLower(key)) {
			return true
		}
	}
	return false
}

func hasExecutableArtifactField(value any) bool {
	pending := []any{value}
	for len(pending) > 0 {
		value := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		switch value := value.(type) {
		case *mapping:
			for _, key := range value.keys {
				name, _ := key.(string)
				if slices.Contains([]string{"argv", "command", "commands", "exec", "hook", "hooks", "install_command", "post_install", "pre_install", "script", "shell"}, strings.ToLower(name)) {
					return true
				}
				pending = append(pending, value.get(key))
			}
		case []any:
			pending = append(pending, value...)
		}
	}
	return false
}
