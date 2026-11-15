package admission

import (
	"encoding/json"
	"errors"
	"io"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type trialSourceScanner struct {
	decoder   *json.Decoder
	target    []string
	keys      []string
	remaining int
}

func trialSourceMemberOrder(source, target string) ([]string, error) {
	if source == "" || !strings.HasPrefix(target, "/") {
		return nil, invalid()
	}
	decoder := json.NewDecoder(strings.NewReader(source))
	decoder.UseNumber()
	scanner := trialSourceScanner{decoder: decoder, target: jsonpointer.Tokens(target), remaining: len(source)}
	if err := scanner.value(0, 0); err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, invalid()
	}
	return scanner.keys, nil
}
func (s *trialSourceScanner) value(matched, depth int) error {
	s.remaining--
	if s.remaining < 0 || depth > 64 {
		return invalid()
	}
	token, err := s.decoder.Token()
	if err != nil {
		return invalid()
	}
	delimiter, compound := token.(json.Delim)
	if !compound {
		return nil
	}
	if delimiter != '{' && delimiter != '[' {
		return invalid()
	}
	return s.members(matched, depth, delimiter)
}
func (s *trialSourceScanner) members(matched, depth int, delimiter json.Delim) error {
	for index := 0; s.decoder.More(); index++ {
		key, err := s.memberKey(index, matched, delimiter)
		if err != nil {
			return err
		}

		next := -1
		if matched >= 0 && matched < len(s.target) && s.target[matched] == key {
			next = matched + 1
		}
		if err := s.value(next, depth+1); err != nil {
			return err
		}
	}
	token, err := s.decoder.Token()
	if err != nil {
		return invalid()
	}
	expected := json.Delim('}')
	if delimiter == '[' {
		expected = ']'
	}
	return require(token == expected)
}

func (s *trialSourceScanner) memberKey(index, matched int, delimiter json.Delim) (string, error) {
	if delimiter != '{' {
		return strconv.Itoa(index), nil
	}
	token, err := s.decoder.Token()
	if err != nil {
		return "", invalid()
	}
	key, ok := token.(string)
	if !ok {
		return "", invalid()
	}
	if matched == len(s.target) {
		s.keys = append(s.keys, key)
	}
	return key, nil
}
