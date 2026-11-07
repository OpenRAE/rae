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
