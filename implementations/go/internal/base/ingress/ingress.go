// Package ingress parses untrusted JSON text before contract validation (Go
// port 06, issue #1779).
//
// Parse follows the strict JSON ingress of the Python reference: json.loads
// with hooks that refuse duplicate members, non-finite numbers, and integers
// beyond 4,300 digits. It accepts and refuses the same texts, reports the same
// codes, and finds the first failure in the same order. One difference is
// deliberate: Parse refuses a UTF-16 surrogate that is not part of a pair,
// because valid UTF-8 cannot hold it and I-JSON (RFC 7493) forbids it.
//
// The parser is custom, because encoding/json gives other results: it keeps
// the last of duplicate members, reads NaN and Infinity as syntax errors,
// replaces an unpaired surrogate and invalid UTF-8 with U+FFFD, and stops at
// 10,000 levels of nesting.
package ingress

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"slices"
	"strconv"
	"strings"
	"unicode"
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
	_ Root = iota
	Object
	Array
)

func (r Root) valid() bool {
	return r == Object || r == Array
}

// Limits bound an input.
type Limits struct {
	// MaxBytes is the largest input length in bytes.
	MaxBytes int
	// MaxDepth is the deepest container nesting, capped at 65,000. Zero selects the decoder
	// limit of 65,000 levels. The Python decoder stops at its C stack limit,
	// which is 65,206 levels on the reference host.
	MaxDepth int
}

const (
	decoderDepth = 65000
	// maxDigits is the integer digit limit of the Python reference.
	maxDigits = 4300
)

// The byte order marks that Python's json.detect_encoding recognizes.
const (
	utf32BE = "\x00\x00\xfe\xff"
	utf32LE = "\xff\xfe\x00\x00"
	utf16BE = "\xfe\xff"
	utf16LE = "\xff\xfe"
	utf8BOM = "\xef\xbb\xbf"
)

// Parse parses data as one JSON value of the root type. An object is a
// map[string]any, an array is a []any, and a number is a json.Number with the
// text of the input.
func Parse(data []byte, limits Limits, root Root) (any, error) {
	if limits.MaxBytes < 1 || limits.MaxDepth < 0 {
		return nil, ErrLimits
	}
	if !root.valid() {
		return nil, &Error{InvalidRoot}
	}
	if len(data) > limits.MaxBytes {
		return nil, &Error{TooLarge}
	}
	if len(bytes.Trim(data, " \t\n\r\v\f")) == 0 {
		return nil, &Error{Empty}
	}
	depth := decoderDepth
	if limits.MaxDepth > 0 {
		depth = min(limits.MaxDepth, decoderDepth)
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
		switch b {
		case '"':
			inString = true
		case '[', '{':
			depth++
			if depth > limit {
				return true
			}
		case ']', '}':
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

// decodeText returns data as UTF-8 text. It detects the encoding and removes a
// byte order mark as Python's json.detect_encoding and its codecs do.
func decodeText(data []byte) (string, bool) {
	if rest, ok := bytes.CutPrefix(data, []byte(utf32BE)); ok {
		return decodeUTF32(rest, binary.BigEndian)
	}
	if rest, ok := bytes.CutPrefix(data, []byte(utf32LE)); ok {
		return decodeUTF32(rest, binary.LittleEndian)
	}
	if rest, ok := bytes.CutPrefix(data, []byte(utf16BE)); ok {
		return decodeUTF16(rest, binary.BigEndian)
	}
	if rest, ok := bytes.CutPrefix(data, []byte(utf16LE)); ok {
		return decodeUTF16(rest, binary.LittleEndian)
	}
	if rest, ok := bytes.CutPrefix(data, []byte(utf8BOM)); ok {
		return string(rest), utf8.Valid(rest)
	}
	return decodeUnmarked(data)
}

// decodeUnmarked decodes text without a byte order mark. Its zero bytes select
// the encoding, as in json.detect_encoding.
func decodeUnmarked(data []byte) (string, bool) {
	if len(data) >= 4 && data[0] == 0 {
		if data[1] != 0 {
			return decodeUTF16(data, binary.BigEndian)
		}
		return decodeUTF32(data, binary.BigEndian)
	}
	if len(data) >= 4 && data[1] == 0 {
		if data[2] != 0 || data[3] != 0 {
			return decodeUTF16(data, binary.LittleEndian)
		}
		return decodeUTF32(data, binary.LittleEndian)
	}
	if len(data) == 2 && data[0] == 0 {
		return decodeUTF16(data, binary.BigEndian)
	}
	if len(data) == 2 && data[1] == 0 {
		return decodeUTF16(data, binary.LittleEndian)
	}
	return string(data), utf8.Valid(data)
}

// decodeUTF16 decodes UTF-16 text. It refuses an odd length and a surrogate
// that is not part of a pair.
func decodeUTF16(data []byte, order binary.ByteOrder) (string, bool) {
	if len(data)%2 != 0 {
		return "", false
	}
	units := make([]uint16, len(data)/2)
	for i := range units {
		units[i] = order.Uint16(data[2*i:])
	}
	runes := utf16.Decode(units)
	// Decode replaces an unpaired surrogate with U+FFFD, so the runes then
	// encode to other units.
	return string(runes), slices.Equal(utf16.Encode(runes), units)
}

// decodeUTF32 decodes UTF-32 text. It refuses a length that is not a multiple
// of four, a surrogate, and a value above U+10FFFF.
func decodeUTF32(data []byte, order binary.ByteOrder) (string, bool) {
	if len(data)%4 != 0 {
		return "", false
	}
	var text strings.Builder
	for i := 0; i < len(data); i += 4 {
		value := order.Uint32(data[i:])
		if value > unicode.MaxRune || utf16.IsSurrogate(rune(value)) {
			return "", false
		}
		text.WriteRune(rune(value))
	}
	return text.String(), true
}

// parser reads the JSON grammar of Python's json module.
type parser struct {
	text     string
	pos      int
	maxDepth int
}

// peek returns the byte at offset from the position, or zero after the end.
// A zero byte is not valid outside a string, so the parser reads it as the end.
func (p *parser) peek(offset int) byte {
	if i := p.pos + offset; i < len(p.text) {
		return p.text[i]
	}
	return 0
}

func (p *parser) space() {
	for strings.ContainsRune(" \t\n\r", rune(p.peek(0))) {
		p.pos++
	}
}

func (p *parser) value(depth int) (any, error) {
	if p.skip("NaN") || p.skip("Infinity") || p.skip("-Infinity") {
		return nil, &Error{NonFinite}
	}
	if value, ok := p.literal(); ok {
		return value, nil
	}
	switch p.peek(0) {
	case '"':
		return p.str()
	case '[', '{':
		if depth >= p.maxDepth {
			return nil, &Error{TooDeep}
		}
		if p.peek(0) == '[' {
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
	if p.space(); p.peek(0) == ']' {
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
		next := p.peek(0)
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
	if p.space(); p.peek(0) == '}' {
		p.pos++
		return map[string]any{}, nil
	}
	for {
		if p.peek(0) != '"' {
			return nil, &Error{Invalid}
		}
		key, err := p.str()
		if err != nil {
			return nil, err
		}
		if p.space(); p.peek(0) != ':' {
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
		next := p.peek(0)
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
	c := p.peek(0)
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
		if !strings.HasPrefix(p.text[p.pos:], `\u`) {
			return &Error{Invalid}
		}
		p.pos += 2
		low, ok := p.unit()
		if !ok {
			return &Error{Invalid}
		}
		// DecodeRune returns U+FFFD unless r is a high and low a low surrogate.
		if r = utf16.DecodeRune(r, rune(low)); r == utf8.RuneError {
			return &Error{Invalid}
		}
	}
	out.WriteRune(r)
	return nil
}

// unit reads four hexadecimal digits.
func (p *parser) unit() (uint16, bool) {
	digits := p.text[p.pos:min(p.pos+4, len(p.text))]
	// ParseUint takes only hexadecimal digits: no sign, prefix, or underscore.
	value, err := strconv.ParseUint(digits, 16, 16)
	if err != nil || len(digits) != 4 {
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
	if p.peek(0) == '.' && isDigit(p.peek(1)) {
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
	for isDigit(p.peek(0)) {
		p.pos++
	}
	return p.pos > start
}

func isDigit(c byte) bool {
	return '0' <= c && c <= '9'
}
