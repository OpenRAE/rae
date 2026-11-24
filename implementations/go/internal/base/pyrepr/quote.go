// Package pyrepr preserves reference quoted string presentation.
package pyrepr

import (
	"fmt"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/rangetable"
)

// Quote returns the reference Unicode 16 spelling for a quoted string.
// Callers use it for diagnostic identifiers and deterministic comparison keys.
func Quote(value string) string {
	quote := '\''
	if strings.ContainsRune(value, '\'') && !strings.ContainsRune(value, '"') {
		quote = '"'
	}
	var result strings.Builder
	assigned := rangetable.Assigned("16.0.0")
	result.WriteRune(quote)
	for _, r := range value {
		writeQuotedRune(&result, r, quote, assigned)
	}
	result.WriteRune(quote)
	return result.String()
}
func writeQuotedRune(result *strings.Builder, r, quote rune, assigned *unicode.RangeTable) {
	switch {
	case r == quote || r == '\\':
		result.WriteRune('\\')
		result.WriteRune(r)
	case r == '\t':
		result.WriteString(`\t`)
	case r == '\n':
		result.WriteString(`\n`)
	case r == '\r':
		result.WriteString(`\r`)
	case unicode.IsPrint(r) && unicode.Is(assigned, r):
		result.WriteRune(r)
	case r <= 0xff:
		fmt.Fprintf(result, `\x%02x`, r)
	case r <= 0xffff:
		fmt.Fprintf(result, `\u%04x`, r)
	default:
		fmt.Fprintf(result, `\U%08x`, r)
	}
}
