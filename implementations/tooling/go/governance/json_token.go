package governance

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"regexp"
	"strings"
)

type jsonSyntaxError struct {
	message                string
	position, line, column int
}

func (e *jsonSyntaxError) Error() string {
	return fmt.Sprintf("%s: line %d column %d (char %d)", e.message, e.line, e.column, e.position)
}

func (r *jsonReader) syntax(message string) error { return jsonSyntax(r.source, r.position, message) }

func jsonSyntax(source []byte, position int, message string) error {
	position = min(position, len(source))
	line := bytes.Count(source[:position], []byte{'\n'}) + 1
	last := bytes.LastIndexByte(source[:position], '\n')
	column := len([]rune(string(source[last+1:position]))) + 1
	return &jsonSyntaxError{message: message, position: len([]rune(string(source[:position]))), line: line, column: column}
}

func (r *jsonReader) space() {
	for r.position < len(r.source) && strings.ContainsRune(" \t\n\r", rune(r.source[r.position])) {
		r.position++
	}
}

func (r *jsonReader) take(want byte) bool {
	if r.position >= len(r.source) || r.source[r.position] != want {
		return false
	}
	r.position++
	return true
}

func (r *jsonReader) token() (any, error) {
	r.space()
	if r.position >= len(r.source) {
		return nil, r.syntax("Expecting value")
	}
	switch r.source[r.position] {
	case '[', '{':
		kind := json.Delim(r.source[r.position])
		r.position++
		return kind, nil
	case '"':
		return r.stringToken()
	}
	for _, constant := range []struct {
		text  string
		value any
	}{{nullLiteral, nil}, {trueLiteral, true}, {"false", false}, {"NaN", math.NaN()}, {"Infinity", math.Inf(1)}, {"-Infinity", math.Inf(-1)}} {
		if bytes.HasPrefix(r.source[r.position:], []byte(constant.text)) {
			r.position += len(constant.text)
			return constant.value, nil
		}
	}
	number := regexp.MustCompile(`^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?`).Find(r.source[r.position:])
	if number == nil {
		return nil, r.syntax("Expecting value")
	}
	r.position += len(number)
	return jsonNumber(json.Number(number))
}

func (r *jsonReader) stringToken() (string, error) {
	start := r.position
	end := jsonQuotedEnd(r.source, start)
	if end >= len(r.source) {
		return "", r.syntax("Unterminated string starting at")
	}
	raw := r.source[start : end+1]
	var validated string
	if err := json.Unmarshal(raw, &validated); err != nil {
		return "", jsonStringFailure(r.source, start, err)
	}
	r.position = end + 1
	return jsonString(raw), nil
}

func jsonStringFailure(source []byte, start int, err error) error {
	syntax, ok := errors.AsType[*json.SyntaxError](err)
	if !ok {
		return err
	}
	position := start + int(syntax.Offset) - 1
	message := "Invalid \\escape"
	if position >= 0 && position < len(source) && source[position] < 32 {
		message = "Invalid control character at"
	} else {
		position--
	}
	if strings.Contains(syntax.Error(), "hexadecimal") {
		message = "Invalid \\uXXXX escape"
	}
	return jsonSyntax(source, max(start, position), message)
}
