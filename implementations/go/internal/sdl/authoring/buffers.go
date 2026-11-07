package authoring

import (
	"math"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// Work ceilings are separate from language-level source/composition charges.
func jsonWorkingLimit(bytes int64, nodes int) int64 {
	if bytes > math.MaxInt64/6 || int64(nodes) > (math.MaxInt64-6*bytes)/128 {
		return math.MaxInt64
	}
	return 6*bytes + 128*int64(nodes)
}

type copyBudget struct{ remaining int64 }

func (b *copyBudget) reserve(count int64) error {
	if count < 0 || count > b.remaining {
		return importError("budget-exceeded")
	}
	b.remaining -= count
	return nil
}

// Resolve tokens first, then reserve the entire allocation. No append occurs
// while the result length is unknown. Input and unchanged replacement bytes
// remain shared; only newly created results consume the copy allowance.
func (b *copyBudget) replace(value string, resolve func(string, string) (string, error)) (string, error) {
	matches := variableTokens.FindAllStringSubmatchIndex(value, -1)
	if len(matches) == 0 {
		return value, nil
	}
	replacements := make([]string, len(matches))
	size := int64(len(value))
	changed := false
	for i, match := range matches {
		token := value[match[0]:match[1]]
		replacement, err := resolve(token, value[match[2]:match[3]])
		if err != nil {
			return "", err
		}
		replacements[i] = replacement
		if replacement != token {
			changed = true
		}
		size -= int64(len(token))
		if int64(len(replacement)) > math.MaxInt64-size {
			return "", importError("budget-exceeded")
		}
		size += int64(len(replacement))
	}
	if !changed {
		return value, nil
	}
	if size > int64(math.MaxInt) {
		return "", importError("budget-exceeded")
	}
	if err := b.reserve(size); err != nil {
		return "", err
	}
	var result strings.Builder
	result.Grow(int(size))
	previous := 0
	for i, match := range matches {
		result.WriteString(value[previous:match[0]])
		result.WriteString(replacements[i])
		previous = match[1]
	}
	result.WriteString(value[previous:])
	return result.String(), nil
}

func compositionJSONWork(limits source.Limits) int64 {
	local := jsonWorkingLimit(limits.MaxComposedBytes, limits.MaxComposedNodes)
	depth := int64(limits.MaxCompositionDepth)
	if depth == math.MaxInt64 || local > math.MaxInt64/(depth+1) {
		return math.MaxInt64
	}
	return local * (depth + 1)
}
