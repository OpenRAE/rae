package source

import (
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Render writes canonical YAML presentation of the decoded, normalized source.
// It does not expand SDL shorthands, apply model defaults or admit a scenario.
// The model owner must supply its normalized field order before command formatting.
func (d *Document) Render(maxBytes int64) ([]byte, error) {
	if maxBytes < 1 {
		return nil, importFailure(budgetExceededCode)
	}
	e := emitter{limit: maxBytes,
		integer:   regexp.MustCompile(`^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$`),
		float:     regexp.MustCompile(`^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$`),
		timestamp: regexp.MustCompile(`^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?)$`),
	}
	e.node(d.root, d.keyScope, 0, "")
	if d.root.kind == 'v' && e.out.Len() > 0 && !strings.HasPrefix(e.out.String(), "'") && !strings.HasPrefix(e.out.String(), "\"") {
		e.write("...\n")
	}
	if e.err != nil {
		return nil, e.err
	}
	return []byte(e.out.String()), nil
}

type emitter struct {
	out                       strings.Builder
	limit                     int64
	err                       error
	integer, float, timestamp *regexp.Regexp
}

func (e *emitter) write(text string) {
	if e.err != nil {
		return
	}
	if int64(len(text)) > e.limit-int64(e.out.Len()) {
		e.err = importFailure(budgetExceededCode)
		return
	}
	e.out.WriteString(text)
}
func (e *emitter) node(n *node, scope string, indent int, prefix string) {
	if e.err != nil {
		return
	}
	switch n.kind {
	case 'm':
		e.mapping(n, scope, indent, prefix)
	case 's':
		e.sequence(n, scope, indent, prefix)
	default:
		e.write(prefix)
		e.write(e.scalar(n.value, indent))
		e.write("\n")
	}
}
func (e *emitter) inline(n *node) bool {
	return n.kind == 'v' || n.kind == 'm' && len(n.entries) == 0 || n.kind == 's' && len(n.children) == 0
}
func (e *emitter) value(n *node, scope string, indent int, prefix string) {
	if n.kind == 'm' && len(n.entries) == 0 {
		e.write(prefix + "{}\n")
		return
	}
	if n.kind == 's' && len(n.children) == 0 {
		e.write(prefix + "[]\n")
		return
	}
	e.node(n, scope, indent, prefix)
}
func (e *emitter) mapping(n *node, scope string, indent int, prefix string) {
	if len(n.entries) == 0 {
		e.write(prefix + "{}\n")
		return
	}
	pad := strings.Repeat(" ", indent)
	for i, entry := range n.entries {
		if e.err != nil {
			return
		}
		key, _ := entry.key.value.(string)
		key = canonical(key, scope)
		lead := pad
		if i == 0 && prefix != "" {
			lead = prefix
		}
		e.mappingEntry(entry, key, scope, indent, lead)
	}
}
func (e *emitter) mappingEntry(entry member, key, scope string, indent int, lead string) {
	simple := utf8.RuneCountInString(key)+5 < 128 && key != "" && !strings.ContainsRune(key, '\n')
	rendered := e.mappingKey(key, indent, simple)
	child := childScope(scope, key, entry.value)
	if !simple {
		e.write(lead + "? " + rendered + "\n")
		lead = strings.Repeat(" ", indent) + ":"
	} else {
		lead += rendered + ":"
	}
	if e.inline(entry.value) {
		e.value(entry.value, child, indent+2, lead+" ")
		return
	}
	e.write(lead + "\n")
	next := indent + 2
	if entry.value.kind == 's' {
		next = indent
	}
	e.node(entry.value, child, next, "")
}

func (e *emitter) mappingKey(key string, indent int, simple bool) string {
	if !simple {
		return e.scalar(key, indent+2)
	}
	if needsDouble(key) {
		return doublePresentation(key, indent+2, indent, false)
	}
	if strings.TrimSpace(key) != key || e.resolved(key) || indicator(key) {
		return "'" + strings.ReplaceAll(key, "'", "''") + "'"
	}
	return key
}

func (e *emitter) sequence(n *node, scope string, indent int, prefix string) {
	if len(n.children) == 0 {
		e.write(prefix + "[]\n")
		return
	}
	pad := strings.Repeat(" ", indent)
	for i, child := range n.children {
		if e.err != nil {
			return
		}
		lead := pad + "- "
		if i == 0 && prefix != "" {
			lead = prefix + "- "
		}
		e.value(child, scope, indent+2, lead)
	}
}
func (e *emitter) scalar(value any, indent int) string {
	switch v := value.(type) {
	case nil:
		return nullText
	case bool:
		if v {
			return trueText
		}
		return falseText
	case json.Number:
		return string(v)
	case float64:
		return pythonFloat(v)
	case string:
		return e.string(v, indent)
	default:
		panic("source value invariant")
	}
}
func pythonFloat(value float64) string {
	format := byte('f')
	absolute := math.Abs(value)
	if absolute != 0 && (absolute < 1e-4 || absolute >= 1e16) {
		format = 'e'
	}
	text := strconv.FormatFloat(value, format, -1, 64)
	mantissa, exponent, scientific := strings.Cut(text, "e")
	if !strings.Contains(mantissa, ".") {
		mantissa += ".0"
	}
	if scientific {
		return mantissa + "e" + exponent
	}
	return mantissa
}
func (e *emitter) string(text string, indent int) string {
	double := needsDouble(text)
	if double {
		return doublePresentation(text, indent, e.column(), true)
	}
	unsafe := text == "" || strings.TrimSpace(text) != text || strings.ContainsAny(text, "\n") || e.resolved(text) || indicator(text)
	if !unsafe {
		return e.wrap(text, indent, false)
	}
	return e.singleQuoted(text, indent)
}
func needsDouble(text string) bool {
	for _, c := range text {
		if c > 126 || c < 32 && c != '\n' {
			return true
		}
	}
	return strings.Contains(text, " \n") || strings.Contains(text, "\n ") || strings.HasSuffix(text, " ") && strings.ContainsRune(text, '\n')
}
func (e *emitter) singleQuoted(text string, indent int) string {
	escaped := strings.ReplaceAll(text, "'", "''")
	var out strings.Builder
	for i := 0; i < len(escaped); i++ {
		if escaped[i] != '\n' {
			out.WriteByte(escaped[i])
			continue
		}
		count := 1
		for i+1 < len(escaped) && escaped[i+1] == '\n' {
			count++
			i++
		}
		out.WriteString(strings.Repeat("\n", count+1))
		out.WriteString(strings.Repeat(" ", indent))
	}
	return "'" + e.wrap(out.String(), indent, true) + "'"
}
func (e *emitter) resolved(text string) bool {
	if inWords(text, "yes Yes YES no No NO true True TRUE false False FALSE on On ON off Off OFF null Null NULL ~") {
		return true
	}
	return e.integer.MatchString(text) || e.float.MatchString(text) || e.timestamp.MatchString(text)
}
func indicator(text string) bool {
	if text == "" || strings.HasPrefix(text, "---") || strings.HasPrefix(text, "...") {
		return true
	}
	if strings.ContainsAny(text[:1], "#,[]{}&*!|>'\"%@`") {
		return true
	}
	if text[0] == '-' || text[0] == '?' || text[0] == ':' {
		if len(text) == 1 || text[1] == ' ' || text[1] == '\n' {
			return true
		}
	}
	return strings.Contains(text, ": ") || strings.HasSuffix(text, ":") || strings.Contains(text, " #")
}

// Double-quoted scalars split only at a space or an escaped-rune boundary.
// Long plain ASCII runs remain intact, as in the reference YAML presentation.
type quotedWriter struct {
	out                     strings.Builder
	raw                     []rune
	indent, column, pending int
	split                   bool
}

func doublePresentation(text string, indent, column int, split bool) string {
	writer := quotedWriter{raw: []rune(text), indent: indent, column: column + 1, split: split}
	writer.out.WriteByte('"')
	for i := 0; i <= len(writer.raw); i++ {
		writer.step(i)
	}
	writer.out.WriteByte('"')
	return writer.out.String()
}
func (w *quotedWriter) step(index int) {
	if index == len(w.raw) || escapeNeeded(w.raw[index]) {
		w.out.WriteString(string(w.raw[w.pending:index]))
		w.column += index - w.pending
		w.pending = index
		if index < len(w.raw) {
			escaped := escapeRune(w.raw[index])
			w.out.WriteString(escaped)
			w.column += len(escaped)
			w.pending = index + 1
		}
	}
	if quoteBreak(w.raw, index, w.pending, w.column, w.split) {
		w.fold(index)
	}
}
func (w *quotedWriter) fold(index int) {
	if w.pending < index {
		w.out.WriteString(string(w.raw[w.pending:index]))
		w.pending = index
	}
	w.out.WriteString("\\\n")
	w.out.WriteString(strings.Repeat(" ", w.indent))
	w.column = w.indent
	if w.raw[w.pending] == ' ' {
		w.out.WriteByte('\\')
		w.column++
	}
}
func quoteBreak(raw []rune, index, pending, column int, split bool) bool {
	if !split || index <= 0 || index >= len(raw)-1 {
		return false
	}
	return (raw[index] == ' ' || pending >= index) && column+index-pending > 80
}
func escapeNeeded(c rune) bool { return c < ' ' || c > '~' || c == '"' || c == '\\' }
func escapeRune(c rune) string {
	switch c {
	case 0:
		return `\0`
	case 7:
		return `\a`
	case 8:
		return `\b`
	case 9:
		return `\t`
	case 10:
		return `\n`
	case 11:
		return `\v`
	case 12:
		return `\f`
	case 13:
		return `\r`
	case 27:
		return `\e`
	case '"':
		return `\"`
	case '\\':
		return `\\`
	case 0x85:
		return `\N`
	case 0xa0:
		return `\_`
	case 0x2028:
		return `\L`
	case 0x2029:
		return `\P`
	default:
		if c <= 255 {
			return fmt.Sprintf(`\x%02X`, c)
		}
		if c <= 65535 {
			return fmt.Sprintf(`\u%04X`, c)
		}
		return fmt.Sprintf(`\U%08X`, c)
	}
}
func (e *emitter) wrap(text string, indent int, quoted bool) string {
	column := e.column()
	if quoted {
		column++
	}
	var out strings.Builder
	for i, c := range text {
		if c == ' ' && i > 0 && i+1 < len(text) && text[i-1] != ' ' && text[i+1] != ' ' && column > 80 {
			out.WriteByte('\n')
			out.WriteString(strings.Repeat(" ", indent))
			column = indent
			continue
		}
		out.WriteRune(c)
		if c == '\n' {
			column = 0
		} else {
			column++
		}
	}
	return out.String()
}
func (e *emitter) column() int {
	text := e.out.String()
	if i := strings.LastIndexByte(text, '\n'); i >= 0 {
		return len(text) - i - 1
	}
	return len(text)
}
