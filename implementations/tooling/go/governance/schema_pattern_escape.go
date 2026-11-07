package governance

import (
	"strconv"
	"strings"
)

func schemaLiteralEscape(text string, inClass, python bool) (string, int, error) {
	if !python && !javascriptEscapeAllowed(text[0], inClass) {
		return "", 0, errSchemaPattern
	}
	switch text[0] {
	case '0':
		if !python {
			return javascriptNullEscape(text)
		}
	case 'u':
		return schemaHexEscape(text, 4, `\x{`, `}`)
	case 'x':
		return schemaHexEscape(text, 2, `\x`, "")
	case 'A', 'a', 'Z', 'b', 'B':
		spelling, allowed := schemaAnchorEscape(text[0], inClass, python)
		if !allowed {
			return "", 0, errSchemaPattern
		}
		return spelling, 1, nil
	case 'Q', 'E', 'p', 'P', 'z', 'N', 'U':
		return "", 0, errSchemaPattern
	}
	return `\` + text[:1], 1, nil
}

func schemaHexEscape(text string, length int, prefix, suffix string) (string, int, error) {
	if len(text) <= length {
		return "", 0, errSchemaPattern
	}
	if _, err := strconv.ParseUint(text[1:1+length], 16, length*4); err != nil {
		return "", 0, errSchemaPattern
	}
	return prefix + text[1:1+length] + suffix, length + 1, nil
}

func javascriptEscapeAllowed(char byte, inClass bool) bool {
	if char == '-' {
		return inClass
	}
	return strings.ContainsRune(`bBfnrtvuUx0^$\.*+?()[]{}|/`, rune(char))
}

func javascriptNullEscape(text string) (string, int, error) {
	if len(text) > 1 && text[1] >= '0' && text[1] <= '9' {
		return "", 0, errSchemaPattern
	}
	return `\x00`, 1, nil
}

func schemaAnchorEscape(char byte, inClass, python bool) (string, bool) {
	switch char {
	case 'A':
		return `\A`, python && !inClass
	case 'a':
		return `\a`, python
	case 'Z':
		return `\z`, python && !inClass
	case 'b':
		if inClass {
			return `\x08`, true
		}
		return `\b`, !python
	case 'B':
		return `\B`, !python && !inClass
	default:
		return "", false
	}
}
