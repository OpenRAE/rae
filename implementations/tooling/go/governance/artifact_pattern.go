package governance

import (
	"regexp"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

const toolingManifestPattern = "^(?!/)(?![A-Za-z]:)(?!.*\\\\)(?!.*(?:^|/)\\.{1,2}(?:/|$))[^\\u0000]+$"

var toolingDotComponent = regexp.MustCompile(`(?:^|/)\.{1,2}(?:/|\n?\z)`)

type toolingPathPattern struct{}

func (toolingPathPattern) String() string { return toolingManifestPattern }
func (toolingPathPattern) MatchString(name string) bool {
	if name == "" || strings.ContainsRune(name, 0) || strings.HasPrefix(name, "/") || manifestDrivePrefix(name) {
		return false
	}
	firstLine, _, _ := strings.Cut(name, "\n")
	if strings.Contains(firstLine, `\`) {
		return false
	}
	// The reference's negative .* lookaheads stop at LF. Their trailing $
	// still refers to the complete input, including its optional final LF.
	location := toolingDotComponent.FindStringIndex(name)
	return location == nil || location[0] > len(firstLine)
}
func manifestDrivePrefix(name string) bool {
	return len(name) >= 2 && name[1] == ':' && (name[0] >= 'A' && name[0] <= 'Z' || name[0] >= 'a' && name[0] <= 'z')
}

//nolint:ireturn // The schema compiler's existing callback requires this interface.
func compileToolingPattern(source string) (jsonschema.Regexp, error) {
	if source == toolingManifestPattern {
		return toolingPathPattern{}, nil
	}
	return compileSchemaPattern(source)
}
