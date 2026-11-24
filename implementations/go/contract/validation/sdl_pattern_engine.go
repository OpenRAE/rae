package validation

import "strings"

// The pinned field engine uses Unicode White_Space and a strict end anchor.
// Preserve those facts through the published-schema regex adapter.
const rustSDLWhitespace = `\t\n\v\f\r\x85\p{Z}`

func rustSDLPattern(source string) (string, error) {
	var result strings.Builder
	inClass := false
	for index := 0; index < len(source); index++ {
		c := source[index]
		if c == '\\' && index+1 < len(source) {
			index++
			escape, err := rustSDLEscape(source[index], inClass)
			if err != nil {
				return "", err
			}
			result.WriteString(escape)
			continue
		}
		switch c {
		case '[':
			inClass = true
		case ']':
			inClass = false
		}
		if c == '$' && !inClass {
			result.WriteString(`\z`)
		} else {
			result.WriteByte(c)
		}
	}
	pattern := result.String()
	if _, err := compilePattern(pattern); err != nil {
		return "", sdlPatternInvalid()
	}
	return pattern, nil
}

func rustSDLEscape(c byte, inClass bool) (string, error) {
	switch c {
	case 's':
		if inClass {
			return rustSDLWhitespace, nil
		}
		return "[" + rustSDLWhitespace + "]", nil
	case 'S':
		if inClass {
			return "", sdlPatternInvalid()
		}
		return "[^" + rustSDLWhitespace + "]", nil
	case 'd':
		return `\p{Nd}`, nil
	default:
		return "\\" + string(c), nil
	}
}
