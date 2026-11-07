package governance

import (
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

// jsonReader uses iterative containers and standard-library scalar validation,
// retaining the reference reader's
// member order, integer bound, float values and lone escaped surrogates.
// Product admission has a different profile and remains a separate check.
type jsonReader struct {
	position int
	source   []byte
	unique   bool
}

type jsonPair struct {
	key   string
	value any
}
type jsonFrame struct {
	kind  json.Delim
	items []any
	pairs []jsonPair
	key   string
}

type jsonPart struct {
	value     any
	container json.Delim
	finished  bool
}

// Match base/ingress.Limits' existing decoder cap. The reference's C-stack
// boundary depends on process state; the native owner fixes it at 65,000.
const governanceJSONDepth = 65000

type jsonDepthError struct{}

func (jsonDepthError) Error() string { return "JSON source exceeds the decoder depth limit" }

func decodeJSON(data []byte, limit int, unique bool) (any, error) {
	if limit > 0 && len(data) > limit {
		return nil, errors.New("JSON source exceeds its byte limit")
	}
	if !utf8.Valid(data) {
		return nil, errors.New("JSON source is not UTF-8")
	}
	r := jsonReader{source: data, unique: unique}
	value, err := r.read()
	if err != nil {
		return nil, err
	}
	r.space()
	if r.position != len(data) {
		return nil, r.syntax("Extra data")
	}
	if _, object := value.(*mapping); unique && !object {
		return nil, errors.New("JSON source must contain an object")
	}
	return value, nil
}

func (r *jsonReader) read() (any, error) {
	value, err := r.token()
	if err != nil {
		return nil, err
	}
	kind, container := value.(json.Delim)
	if !container {
		return value, nil
	}
	stack := []jsonFrame{{kind: kind}}
	for len(stack) > 0 {
		frame := &stack[len(stack)-1]
		part, err := r.advance(frame)
		if err != nil {
			return nil, err
		}
		if part.finished {
			stack = stack[:len(stack)-1]
			if len(stack) == 0 {
				return part.value, nil
			}
			stack[len(stack)-1].append(part.value)
			continue
		}
		if part.container == 0 {
			frame.append(part.value)
			continue
		}
		stack, err = pushJSONFrame(stack, part.container)
		if err != nil {
			return nil, err
		}
	}
	return nil, errors.New("incomplete JSON value")
}

func pushJSONFrame(stack []jsonFrame, kind json.Delim) ([]jsonFrame, error) {
	if len(stack) >= governanceJSONDepth {
		return nil, jsonDepthError{}
	}
	return append(stack, jsonFrame{kind: kind}), nil
}

func (r *jsonReader) advance(frame *jsonFrame) (jsonPart, error) {
	r.space()
	closing := byte(']')
	if frame.kind == '{' {
		closing = '}'
	}
	if r.take(closing) {
		value, err := frame.finish(r.unique)
		return jsonPart{value: value, finished: true}, err
	}
	if len(frame.items) > 0 || len(frame.pairs) > 0 {
		if !r.take(',') {
			return jsonPart{}, r.syntax("Expecting ',' delimiter")
		}
		r.space()
	}
	if frame.kind == '{' {
		if r.position >= len(r.source) || r.source[r.position] != '"' {
			return jsonPart{}, r.syntax("Expecting property name enclosed in double quotes")
		}
		key, err := r.stringToken()
		if err != nil {
			return jsonPart{}, err
		}
		frame.key = key
		r.space()
		if !r.take(':') {
			return jsonPart{}, r.syntax("Expecting ':' delimiter")
		}
	}
	value, err := r.token()
	kind, _ := value.(json.Delim)
	return jsonPart{value: value, container: kind}, err
}

func (f *jsonFrame) append(value any) {
	if f.kind == '{' {
		f.pairs = append(f.pairs, jsonPair{f.key, value})
	} else {
		f.items = append(f.items, value)
	}
}

func (f *jsonFrame) finish(unique bool) (any, error) {
	if f.kind != '{' {
		if f.items == nil {
			f.items = []any{}
		}
		return f.items, nil
	}
	m := newMapping()
	for _, pair := range f.pairs {
		if unique && m.has(pair.key) {
			return nil, errors.New("duplicate JSON key " + pythonRepr(pair.key))
		}
		m.set(pair.key, pair.value)
	}
	return m, nil
}

func jsonNumber(value json.Number) (any, error) {
	if !strings.ContainsAny(string(value), ".eE") {
		if len(strings.TrimPrefix(string(value), "-")) > 4300 {
			return nil, errors.New("JSON contains an integer beyond the digit limit")
		}
		if value == "-0" {
			value = "0"
		}
		return value, nil
	}
	number, err := strconv.ParseFloat(string(value), 64)
	if errors.Is(err, strconv.ErrRange) {
		return number, nil
	}
	return number, err
}

func jsonQuotedEnd(data []byte, start int) int {
	for i := start + 1; i < len(data); i++ {
		if data[i] == '\\' {
			i++
			continue
		}
		if data[i] == '"' {
			return i
		}
	}
	return len(data)
}

func jsonString(raw []byte) string {
	var out strings.Builder
	for i := 1; i < len(raw)-1; i++ {
		if raw[i] != '\\' {
			out.WriteByte(raw[i])
			continue
		}
		i++
		switch raw[i] {
		case '"', '\\', '/':
			out.WriteByte(raw[i])
		case 'b':
			out.WriteByte('\b')
		case 'f':
			out.WriteByte('\f')
		case 'n':
			out.WriteByte('\n')
		case 'r':
			out.WriteByte('\r')
		case 't':
			out.WriteByte('\t')
		case 'u':
			var r rune
			r, i = jsonUnicode(raw, i)
			if r >= 0xd800 && r <= 0xdfff {
				out.Write([]byte{0xe0 | byte(r>>12), 0x80 | byte((r>>6)&0x3f), 0x80 | byte(r&0x3f)})
			} else {
				out.WriteRune(r)
			}
		}
	}
	return out.String()
}

func jsonUnicode(raw []byte, index int) (rune, int) {
	code, _ := strconv.ParseUint(string(raw[index+1:index+5]), 16, 16)
	r := rune(code)
	index += 4
	if r >= 0xd800 && r <= 0xdbff && index+6 < len(raw) && raw[index+1] == '\\' && raw[index+2] == 'u' {
		low, _ := strconv.ParseUint(string(raw[index+3:index+7]), 16, 16)
		if low >= 0xdc00 && low <= 0xdfff {
			return utf16.DecodeRune(r, rune(low)), index + 6
		}
	}
	return r, index
}
