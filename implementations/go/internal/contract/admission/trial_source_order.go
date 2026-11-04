package admission

import (
	"encoding/json"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type trialSourceScanner struct {
	decoder *json.Decoder
	target  string
	keys    []string
	visits  int
}

func trialSourceMemberOrder(source, target string) ([]string, error) {
	if source == "" {
		return nil, invalid()
	}
	d := json.NewDecoder(strings.NewReader(source))
	d.UseNumber()
	s := trialSourceScanner{decoder: d, target: target}
	if err := s.value("", 0); err != nil {
		return nil, err
	}
	return s.keys, nil
}

func (s *trialSourceScanner) value(path string, depth int) error {
	s.visits++
	if s.visits > 100000 || depth > 64 {
		return invalid()
	}
	token, err := s.decoder.Token()
	if err != nil {
		return invalid()
	}
	delim, ok := token.(json.Delim)
	if !ok {
		return nil
	}
	if delim != '{' && delim != '[' {
		return invalid()
	}
	return s.members(path, depth, delim)
}

func (s *trialSourceScanner) members(path string, depth int, delim json.Delim) error {
	var token json.Token
	var err error
	var ok bool
	for index := 0; s.decoder.More(); index++ {
		key := strconv.Itoa(index)
		if delim == '{' {
			token, err = s.decoder.Token()
			if err != nil {
				return invalid()
			}
			key, ok = token.(string)
			if !ok {
				return invalid()
			}
			if path == s.target {
				s.keys = append(s.keys, key)
			}
		}
		if err = s.value(path+"/"+jsonpointer.EscapeToken(key), depth+1); err != nil {
			return err
		}
	}
	_, err = s.decoder.Token()
	return require(err == nil)
}
