package validation

import (
	"errors"
	"regexp"
	"strconv"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// Python's Unicode str.isspace set, which its schema regex engine uses.
const whitespace = `\t\n\v\f\r\x1c-\x1f\x85\p{Z}`

type pattern struct {
	*regexp.Regexp

	source string
}

func (p pattern) String() string { return p.source }

// compilePattern translates only syntax present in the published bundle. The
// resulting RE2 program runs in linear time, including on adversarial input.
//
//nolint:ireturn // jsonschema.RegexpEngine requires this exact callback signature.
func compilePattern(source string) (jsonschema.Regexp, error) {
	text := strings.ReplaceAll(source, `$(?![\s\S])`, `\z`)
	var result strings.Builder
	inClass := false
	for i := 0; i < len(text); i++ {
		c := text[i]
		if c == '\\' && i+1 < len(text) {
			translated, consumed, err := patternEscape(text[i+1:], inClass)
			if err != nil {
				return nil, err
			}
			result.WriteString(translated)
			i += consumed
			continue
		}
		switch c {
		case '[':
			inClass = true
		case ']':
			inClass = false
		}
		if c == '$' && !inClass {
			result.WriteString(`(?:\n?\z)`)
		} else {
			result.WriteByte(c)
		}
	}
	compiled, err := regexp.Compile(result.String())
	if err != nil {
		return nil, err
	}
	return pattern{compiled, source}, nil
}

func patternEscape(text string, inClass bool) (string, int, error) {
	switch text[0] {
	case 'd':
		return `\p{Nd}`, 1, nil
	case 'D':
		return `\P{Nd}`, 1, nil
	case 's':
		if inClass {
			return whitespace, 1, nil
		}
		return "[" + whitespace + "]", 1, nil
	case 'S':
		if inClass {
			return "", 0, errors.New("unsupported negated class in class")
		}
		return "[^" + whitespace + "]", 1, nil
	case 'u':
		if len(text) < 5 {
			return "", 0, errors.New("invalid unicode escape")
		}
		digits := text[1:5]
		if _, err := strconv.ParseUint(digits, 16, 16); err != nil {
			return "", 0, err
		}
		return `\x{` + digits + `}`, 5, nil
	default:
		return `\` + text[:1], 1, nil
	}
}
