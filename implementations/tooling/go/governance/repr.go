package governance

import (
	"encoding/json"
	"fmt"
	"math"
	"slices"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

type reprState struct{ active map[any]bool }

func pythonRepr(value any) string { return (&reprState{active: map[any]bool{}}).value(value, 0) }

func (s *reprState) value(value any, depth int) string {
	if depth > 65200 {
		return "..."
	}
	switch v := value.(type) {
	case nil:
		return "None"
	case bool:
		return pythonBool(v)
	case string:
		return pythonString(v, false)
	case json.Number:
		return string(v)
	case float64:
		return pythonFloat(v)
	case yamlDate:
		return fmt.Sprintf("datetime.date(%d, %d, %d)", v.Year(), v.Month(), v.Day())
	case yamlTimestamp:
		return pythonTimestamp(v)
	case yamlBinary:
		return "b" + pythonString(string(v), true)
	case *mapping:
		return s.mapping(v, depth)
	case []any:
		return s.list(v, depth)
	case []string:
		values := make([]any, len(v))
		for i, item := range v {
			values[i] = item
		}
		return s.list(values, depth)
	case yamlSet:
		return s.set(v, depth)
	case yamlTuple:
		return "(" + strings.Join(s.items(v, depth), ", ") + ")"
	default:
		return fmt.Sprint(value)
	}
}

func pythonBool(value bool) string {
	if value {
		return "True"
	}
	return "False"
}

func pythonString(value string, binary bool) string {
	quote := rune('\'')
	if strings.ContainsRune(value, '\'') && !strings.ContainsRune(value, '"') {
		quote = '"'
	}
	var out strings.Builder
	out.WriteRune(quote)
	if binary {
		for i := range len(value) {
			out.WriteString(reprRune(rune(value[i]), quote, true))
		}
	} else {
		for i := 0; i < len(value); {
			r, size := pythonRuneAt(value, i)
			out.WriteString(reprRune(r, quote, false))
			i += size
		}
	}
	out.WriteRune(quote)
	return out.String()
}

func pythonRuneAt(value string, index int) (rune, int) {
	if value[index] == 0xed && index+2 < len(value) && value[index+1] >= 0xa0 && value[index+1] <= 0xbf && value[index+2] >= 0x80 && value[index+2] <= 0xbf {
		r := rune(value[index]&0x0f)<<12 | rune(value[index+1]&0x3f)<<6 | rune(value[index+2]&0x3f)
		return r, 3
	}
	return utf8.DecodeRuneInString(value[index:])
}

func pythonStringLength(value string) int {
	count := 0
	for i := 0; i < len(value); count++ {
		_, width := pythonRuneAt(value, i)
		i += width
	}
	return count
}

func reprRune(r, quote rune, binary bool) string {
	switch {
	case r == quote || r == '\\':
		return "\\" + string(r)
	case r == '\n':
		return `\n`
	case r == '\r':
		return `\r`
	case r == '\t':
		return `\t`
	case unicode.IsGraphic(r) && (!unicode.IsSpace(r) || r == ' ') && (!binary || r < 127):
		return string(r)
	case r < 256:
		return fmt.Sprintf(`\x%02x`, r)
	case r <= 65535:
		return fmt.Sprintf(`\u%04x`, r)
	default:
		return fmt.Sprintf(`\U%08x`, r)
	}
}

func pythonFloat(value float64) string {
	switch {
	case math.IsInf(value, 1):
		return "inf"
	case math.IsInf(value, -1):
		return "-inf"
	case math.IsNaN(value):
		return "nan"
	}
	format := byte('g')
	if absolute := math.Abs(value); absolute >= 1e-4 && absolute < 1e16 {
		format = 'f'
	}
	result := strconv.FormatFloat(value, format, -1, 64)
	if !strings.ContainsAny(result, ".e") {
		result += ".0"
	}
	return result
}

func pythonTimestamp(value yamlTimestamp) string {
	args := fmt.Sprintf("%d, %d, %d, %d, %d", value.Year(), value.Month(), value.Day(), value.Hour(), value.Minute())
	if value.Second() != 0 || value.Nanosecond() != 0 {
		args += fmt.Sprintf(", %d", value.Second())
	}
	if value.Nanosecond() != 0 {
		args += fmt.Sprintf(", %d", value.Nanosecond()/1000)
	}
	if value.aware {
		args += ", tzinfo=" + pythonTimezone(value)
	}
	return "datetime.datetime(" + args + ")"
}

func pythonTimezone(value yamlTimestamp) string {
	_, offset := value.Zone()
	if offset == 0 {
		return "datetime.timezone.utc"
	}
	delta := "seconds=" + strconv.Itoa(offset)
	if offset < 0 {
		delta = "days=-1, seconds=" + strconv.Itoa(86400+offset)
	}
	return "datetime.timezone(datetime.timedelta(" + delta + "))"
}

func (s *reprState) mapping(value *mapping, depth int) string {
	if s.active[value] {
		return "{...}"
	}
	s.active[value] = true
	defer delete(s.active, value)
	items := make([]string, 0, value.size())
	for _, key := range value.keys {
		items = append(items, s.value(key, depth+1)+": "+s.value(value.get(key), depth+1))
	}
	return "{" + strings.Join(items, ", ") + "}"
}

func (s *reprState) items(values []any, depth int) []string {
	items := make([]string, len(values))
	for i, value := range values {
		items[i] = s.value(value, depth+1)
	}
	return items
}

func (s *reprState) list(value []any, depth int) string {
	if len(value) == 0 {
		return "[]"
	}
	id := &value[0]
	if s.active[id] {
		return "[...]"
	}
	s.active[id] = true
	defer delete(s.active, id)
	return "[" + strings.Join(s.items(value, depth), ", ") + "]"
}

func (s *reprState) set(value yamlSet, depth int) string {
	if value.items.size() == 0 {
		return "set()"
	}
	items := s.items(value.items.keys, depth)
	slices.Sort(items)
	return "{" + strings.Join(items, ", ") + "}"
}
