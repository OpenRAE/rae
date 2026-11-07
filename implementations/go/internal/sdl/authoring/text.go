package authoring

import (
	"strings"
	"unicode"

	"golang.org/x/text/cases"
	"golang.org/x/text/language"
)

func lower(value string) string {
	if strings.IndexFunc(value, func(r rune) bool { return r > unicode.MaxASCII }) < 0 {
		return strings.ToLower(value)
	}
	return cases.Lower(language.Und).String(value)
}

func upper(value string) string {
	if strings.IndexFunc(value, func(r rune) bool { return r > unicode.MaxASCII }) < 0 {
		return strings.ToUpper(value)
	}
	return cases.Upper(language.Und).String(value)
}

func asciiDecimalDigits(value string) string {
	if strings.IndexFunc(value, func(r rune) bool { return r > unicode.MaxASCII }) < 0 {
		return value
	}
	var result strings.Builder
	result.Grow(len(value))
	for _, r := range value {
		if digit, ok := decimalDigit(r, true); ok {
			result.WriteByte('0' + digit)
		} else {
			result.WriteRune(r)
		}
	}
	return result.String()
}
