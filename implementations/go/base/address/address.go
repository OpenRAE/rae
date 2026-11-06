// Package address validates the compiled runtime addresses that the processor
// owns (Go port 06, issue #1779).
package address

import (
	"regexp"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// MaxLength is the largest length of a compiled address.
const MaxLength = 2048

// ErrAddress reports a value that is not a canonical compiled address.
var ErrAddress = fault.New(fault.InvalidInput, "compiled-address", nil)

// compiled matches two or more segments separated by dots. A segment is a
// lowercase ASCII letter or digit followed by up to 63 lowercase letters,
// digits, underscores, or hyphens, or the reserved segment "__private".
var compiled = regexp.MustCompile(`^(?:[a-z0-9][a-z0-9_-]{0,63}|__private)(?:\.(?:[a-z0-9][a-z0-9_-]{0,63}|__private))+$`)

// Valid reports whether s is a canonical compiled address.
func Valid(s string) bool {
	return len(s) <= MaxLength && compiled.MatchString(s)
}

// Render joins the non-empty parts with dots and checks that the result is a
// canonical compiled address.
func Render(parts ...string) (string, error) {
	var kept []string
	for _, part := range parts {
		if part != "" {
			kept = append(kept, part)
		}
	}
	address := strings.Join(kept, ".")
	if !Valid(address) {
		return "", ErrAddress
	}
	return address, nil
}

// PlanRoot returns the root segment of the plan addresses of a plan domain.
func PlanRoot(domain string) (string, bool) {
	root, ok := map[string]string{
		"provisioning":  "provision",
		"orchestration": "orchestration",
		"evaluation":    "evaluation",
	}[domain]
	return root, ok
}

// CompilerOwnedTemporalSubject reports whether an SDL compiler owns a temporal
// subject address: an address below "sdl", or the address of an inject
// delivery of a participant behavior specification.
func CompilerOwnedTemporalSubject(address string) bool {
	if strings.HasPrefix(address, "sdl.") {
		return true
	}
	parts := strings.Split(address, ".")
	return len(parts) == 5 && !slices.Contains(parts, "") && parts[0] == "participant" &&
		parts[1] == "behavior-specification" && parts[3] == "inject-delivery"
}
