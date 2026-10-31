// Package ingress parses untrusted JSON text before contract validation (Go
// port 06, issue #1779).
//
// Parse follows the strict JSON ingress of the Python reference: json.loads
// with hooks that refuse duplicate members, non-finite numbers, and integers
// beyond 4,300 digits. It accepts and refuses the same texts, reports the same
// codes, and finds the first failure in the same order. One difference is
// deliberate: Parse refuses a UTF-16 surrogate that is not part of a pair,
// because valid UTF-8 cannot hold it and I-JSON (RFC 7493) forbids it.
package ingress

import (
	"bytes"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

// The codes of a failed parse.
const (
	TooLarge        = "input-too-large"
	Empty           = "empty-input"
	TooDeep         = "input-too-deep"
	Invalid         = "invalid-json"
	DuplicateMember = "duplicate-member"
	NonFinite       = "non-finite-number"
	IntegerTooLong  = "integer-too-long"
	InvalidRoot     = "invalid-root"
)

// Error is a parse failure. Code is one of the failure codes.
type Error struct {
	Code string
}

func (e *Error) Error() string {
	return "ingress: " + e.Code
}

// ErrLimits reports limits that are not valid.
var ErrLimits = errors.New("ingress: MaxBytes must be positive and MaxDepth must not be negative")

// Root is the JSON type of the top-level value.
type Root int

// The root types.
const (
	Object Root = iota + 1
	Array
)

// Limits bound an input.
type Limits struct {
	// MaxBytes is the largest input length in bytes.
	MaxBytes int
	// MaxDepth is the deepest container nesting. Zero selects the decoder
	// limit of 65,000 levels. The Python decoder stops at its C stack limit,
	// which is 65,206 levels on the reference host.
	MaxDepth int
}

const (
	decoderDepth = 65000
	// maxDigits is the integer digit limit of the Python reference.
	maxDigits = 4300
)

// Parse parses data as one JSON value of the root type. An object is a
// map[string]any, an array is a []any, and a number is a json.Number with the
// text of the input.
func Parse(data []byte, limits Limits, root Root) (any, error) {
	if limits.MaxBytes < 1 || limits.MaxDepth < 0 {
		return nil, ErrLimits
	}
	if len(data) > limits.MaxBytes {
		return nil, &Error{TooLarge}
	}
	if len(bytes.Trim(data, " \t\n\r\v\f")) == 0 {
		return nil, &Error{Empty}
	}
	depth := decoderDepth
	if limits.MaxDepth > 0 {
		depth = limits.MaxDepth
		if tooDeep(data, depth) {
			return nil, &Error{TooDeep}
		}
	}
	text, ok := decodeText(data)
	if !ok {
		return nil, &Error{Invalid}
	}
	p := parser{text: text, maxDepth: depth}
	p.space()
	value, err := p.value(0)
	if err != nil {
		return nil, err
	}
	if p.space(); p.pos != len(p.text) {
		return nil, &Error{Invalid}
	}
	_, isObject := value.(map[string]any)
	_, isArray := value.([]any)
	if root == Object && !isObject || root == Array && !isArray {
		return nil, &Error{InvalidRoot}
	}
	return value, nil
}

// tooDeep reports whether the containers of the raw text nest deeper than
// limit. It skips quoted text, as the Python reference does before decoding.
func tooDeep(data []byte, limit int) bool {
	depth, inString, escaped := 0, false, false
	for _, b := range data {
		if inString {
			inString, escaped = advanceQuoted(b, escaped)
			continue
		}
		if b == '"' {
			inString = true
		}
		if b == '[' || b == '{' {
			depth++
			if depth > limit {
				return true
			}
		}
		if b == ']' || b == '}' {
			depth--
		}
	}
	return false
}

// advanceQuoted returns the state after byte b inside quoted text.
func advanceQuoted(b byte, escaped bool) (inString, nowEscaped bool) {
	if escaped {
		return true, false
	}
	if b == '\\' {
		return true, true
	}
	return b != '"', false
}

// decodeText returns data as UTF-8 text. It detects UTF-16 and UTF-32 and
// removes a byte order mark as Python's json.detect_encoding does.
func decodeText(data []byte) (string, bool) {
	switch {
	case bytes.HasPrefix(data, []byte{0, 0, 0xfe, 0xff}):
		return decodeUTF32(data[4:], true)
	case bytes.HasPrefix(data, []byte{0xff, 0xfe, 0, 0}):
		return decodeUTF32(data[4:], false)
	case bytes.HasPrefix(data, []byte{0xfe, 0xff}):
		return decodeUTF16(data[2:], true)
	case bytes.HasPrefix(data, []byte{0xff, 0xfe}):
		return decodeUTF16(data[2:], false)
	case bytes.HasPrefix(data, []byte{0xef, 0xbb, 0xbf}):
		data = data[3:]
	case len(data) >= 4 && data[0] == 0:
		if data[1] != 0 {
			return decodeUTF16(data, true)
		}
		return decodeUTF32(data, true)
	case len(data) >= 4 && data[1] == 0:
		if data[2] != 0 || data[3] != 0 {
			return decodeUTF16(data, false)
		}
		return decodeUTF32(data, false)
	case len(data) == 2 && data[0] == 0:
		return decodeUTF16(data, true)
	case len(data) == 2 && data[1] == 0:
		return decodeUTF16(data, false)
	}
	return string(data), utf8.Valid(data)
}

func decodeUTF16(data []byte, bigEndian bool) (string, bool) {
	if len(data)%2 != 0 {
		return "", false
	}
	units := make([]uint16, len(data)/2)
	for i := range units {
		high, low := data[2*i], data[2*i+1]
		if !bigEndian {
			high, low = low, high
		}
		units[i] = uint16(high)<<8 | uint16(low)
	}
	// utf16.Decode would replace an unpaired surrogate; such text is refused.
	for i := 0; i < len(units); i++ {
		if units[i] >= 0xdc00 && units[i] <= 0xdfff {
			return "", false
		}
		if units[i] >= 0xd800 && units[i] < 0xdc00 {
			if i+1 == len(units) || units[i+1] < 0xdc00 || units[i+1] > 0xdfff {
				return "", false
			}
			i++
		}
	}
	return string(utf16.Decode(units)), true
}

func decodeUTF32(data []byte, bigEndian bool) (string, bool) {
	if len(data)%4 != 0 {
		return "", false
	}
	var text strings.Builder
	for i := 0; i < len(data); i += 4 {
		b := data[i : i+4]
		r := rune(b[0])<<24 | rune(b[1])<<16 | rune(b[2])<<8 | rune(b[3])
		if !bigEndian {
			r = rune(b[3])<<24 | rune(b[2])<<16 | rune(b[1])<<8 | rune(b[0])
		}
		if !utf8.ValidRune(r) {
			return "", false
		}
		text.WriteRune(r)
	}
	return text.String(), true
}

// parser reads the JSON grammar of Python's json module.
type parser struct {
	text     string
	pos      int
	maxDepth int
}

func (p *parser) space() {
	for p.pos < len(p.text) && strings.IndexByte(" \t\n\r", p.text[p.pos]) >= 0 {
		p.pos++
	}
}

func (p *parser) peek() byte {
	if p.pos < len(p.text) {
		return p.text[p.pos]
	}
	return 0
}

func (p *parser) value(depth int) (any, error) {
	if p.skip("NaN") || p.skip("Infinity") || p.skip("-Infinity") {
		return nil, &Error{NonFinite}
	}
	if value, ok := p.literal(); ok {
		return value, nil
	}
	if p.peek() == '"' {
		return p.str()
	}
	if p.peek() == '[' || p.peek() == '{' {
		if depth >= p.maxDepth {
			return nil, &Error{TooDeep}
		}
		if p.peek() == '[' {
			return p.array(depth + 1)
		}
		return p.object(depth + 1)
	}
	return p.number()
}

// literal reads null, true, or false.
func (p *parser) literal() (any, bool) {
	for _, literal := range []struct {
		text  string
		value any
	}{{"null", nil}, {"true", true}, {"false", false}} {
		if p.skip(literal.text) {
			return literal.value, true
		}
	}
	return nil, false
}

func (p *parser) array(depth int) (any, error) {
	p.pos++
	items := []any{}
	if p.space(); p.peek() == ']' {
		p.pos++
		return items, nil
	}
	for {
		item, err := p.value(depth)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
		p.space()
		next := p.peek()
		p.pos++
		if next == ']' {
			return items, nil
		}
		if next != ',' {
			return nil, &Error{Invalid}
		}
		p.space()
	}
}

func (p *parser) object(depth int) (any, error) {
	p.pos++
	var keys []string
	var values []any
	if p.space(); p.peek() == '}' {
		p.pos++
		return map[string]any{}, nil
	}
	for {
		if p.peek() != '"' {
			return nil, &Error{Invalid}
		}
		key, err := p.str()
		if err != nil {
			return nil, err
		}
		if p.space(); p.peek() != ':' {
			return nil, &Error{Invalid}
		}
		p.pos++
		p.space()
		value, err := p.value(depth)
		if err != nil {
			return nil, err
		}
		keys, values = append(keys, key), append(values, value)
		p.space()
		next := p.peek()
		p.pos++
		if next == '}' {
			return members(keys, values)
		}
		if next != ',' {
			return nil, &Error{Invalid}
		}
		p.space()
	}
}

// members builds an object and refuses a duplicate member, as the Python hook
// does when the object closes.
func members(keys []string, values []any) (any, error) {
	object := make(map[string]any, len(keys))
	for i, key := range keys {
		if _, seen := object[key]; seen {
			return nil, &Error{DuplicateMember}
		}
		object[key] = values[i]
	}
	return object, nil
}

func (p *parser) str() (string, error) {
	p.pos++
	var out strings.Builder
	for p.pos < len(p.text) {
		c := p.text[p.pos]
		p.pos++
		if c == '"' {
			return out.String(), nil
		}
		if c < 0x20 {
			return "", &Error{Invalid}
		}
		if c != '\\' {
			out.WriteByte(c)
			continue
		}
		if err := p.escape(&out); err != nil {
			return "", err
		}
	}
	return "", &Error{Invalid}
}

// escape writes the character of the escape after a backslash.
func (p *parser) escape(out *strings.Builder) error {
	if p.pos >= len(p.text) {
		return &Error{Invalid}
	}
	c := p.text[p.pos]
	p.pos++
	if simple := strings.IndexByte(`"\/bfnrt`, c); simple >= 0 {
		out.WriteByte("\"\\/\b\f\n\r\t"[simple])
		return nil
	}
	if c != 'u' {
		return &Error{Invalid}
	}
	unit, ok := p.unit()
	if !ok {
		return &Error{Invalid}
	}
	r := rune(unit)
	if utf16.IsSurrogate(r) {
		if unit >= 0xdc00 || !strings.HasPrefix(p.text[p.pos:], `\u`) {
			return &Error{Invalid}
		}
		p.pos += 2
		low, ok := p.unit()
		if !ok {
			return &Error{Invalid}
		}
		if r = utf16.DecodeRune(r, rune(low)); r == utf8.RuneError {
			return &Error{Invalid}
		}
	}
	out.WriteRune(r)
	return nil
}

// unit reads four hexadecimal digits.
func (p *parser) unit() (uint16, bool) {
	if p.pos+4 > len(p.text) {
		return 0, false
	}
	value, err := strconv.ParseUint(p.text[p.pos:p.pos+4], 16, 16)
	if err != nil {
		return 0, false
	}
	p.pos += 4
	return uint16(value), true
}

// number reads a number with the syntax of Python's json module.
func (p *parser) number() (any, error) {
	start := p.pos
	p.skip("-")
	if !p.skip("0") && !p.digits() {
		return nil, &Error{Invalid}
	}
	integerEnd := p.pos
	isFloat := false
	if p.peek() == '.' && p.pos+1 < len(p.text) && isDigit(p.text[p.pos+1]) {
		p.pos++
		p.digits()
		isFloat = true
	}
	if mark := p.pos; p.skip("e") || p.skip("E") {
		if !p.skip("+") {
			p.skip("-")
		}
		if p.digits() {
			isFloat = true
		} else {
			p.pos = mark
		}
	}
	text := p.text[start:p.pos]
	if !isFloat {
		if len(strings.TrimPrefix(p.text[start:integerEnd], "-")) > maxDigits {
			return nil, &Error{IntegerTooLong}
		}
		return json.Number(text), nil
	}
	if _, err := strconv.ParseFloat(text, 64); err != nil {
		return nil, &Error{NonFinite}
	}
	return json.Number(text), nil
}

func (p *parser) skip(prefix string) bool {
	if strings.HasPrefix(p.text[p.pos:], prefix) {
		p.pos += len(prefix)
		return true
	}
	return false
}

// digits reads one or more ASCII digits.
func (p *parser) digits() bool {
	start := p.pos
	for p.pos < len(p.text) && isDigit(p.text[p.pos]) {
		p.pos++
	}
	return p.pos > start
}

func isDigit(c byte) bool {
	return '0' <= c && c <= '9'
}
