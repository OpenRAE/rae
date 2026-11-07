package governance

import (
	"fmt"
	"strings"
	"sync"
	"unicode"

	"golang.org/x/text/unicode/rangetable"
)

func pythonAssigned() *unicode.RangeTable { return rangetable.Assigned("16.0.0") }

//nolint:gochecknoglobals // Immutable, lazily built Unicode16 class; no request state is cached.
var pythonSchemaDigits = sync.OnceValue(func() string { return schemaUnicodeClass(unicode.Nd) })

//nolint:gochecknoglobals // Immutable, lazily built Unicode16 class; no request state is cached.
var pythonSchemaWord = sync.OnceValue(func() string { return schemaUnicodeClass(rangetable.Merge(unicode.L, unicode.N)) + "_" })

// The reference interpreter uses Unicode16. Intersect maintained assignment
// and category tables rather than making the toolchain's newer characters valid.
func schemaUnicodeClass(category *unicode.RangeTable) string {
	var out strings.Builder
	start, previous := rune(-1), rune(-1)
	flush := func() {
		if start < 0 {
			return
		}
		if start == previous {
			fmt.Fprintf(&out, `\x{%x}`, start)
		} else {
			fmt.Fprintf(&out, `\x{%x}-\x{%x}`, start, previous)
		}
	}
	rangetable.Visit(category, func(r rune) {
		if !unicode.Is(pythonAssigned(), r) {
			return
		}
		if r == previous+1 {
			previous = r
			return
		}
		flush()
		start, previous = r, r
	})
	flush()
	return out.String()
}
