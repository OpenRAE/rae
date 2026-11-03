package admission

import (
	_ "embed"
	"encoding/json"
	"maps"
	"sort"
	"strings"

	"golang.org/x/text/unicode/runenames"
)

// Unicode 16 classification facts match the pinned Python reference. The
// embedded artifact records its Unicode name-alias source and SHA-256 digest.
// It is immutable package data, not a registry of caller expressions.
//
//go:embed python-regex-unicode16.json
var pythonRegexUnicode string

type patternUnicode struct {
	Version  string          `json:"unicode_version"`
	Start    [][2]rune       `json:"start"`
	Continue [][2]rune       `json:"continue"`
	Assigned [][2]rune       `json:"assigned"`
	Aliases  map[string]rune `json:"aliases"`
}

func (p *pythonPattern) unicodeData() *patternUnicode {
	if p.unicode == nil {
		p.unicode = &patternUnicode{}
		if err := json.Unmarshal([]byte(pythonRegexUnicode), p.unicode); err != nil || p.unicode.Version != "16.0.0" {
			p.bad = true
		}
	}
	return p.unicode
}

func patternRuneIn(c rune, ranges [][2]rune) bool {
	index := sort.Search(len(ranges), func(index int) bool { return ranges[index][1] >= c })
	return index < len(ranges) && ranges[index][0] <= c
}

func (p *pythonPattern) identifier(name string) bool {
	if name == "" {
		return false
	}
	first := true
	for _, c := range name {
		if c < 128 {
			if !patternASCIIIdentifier(c, first) {
				return false
			}
		} else {
			data := p.unicodeData()
			ranges := data.Continue
			if first {
				ranges = data.Start
			}
			if !patternRuneIn(c, ranges) {
				return false
			}
		}
		first = false
	}
	return true
}

func (p *pythonPattern) namedCharacter(name string) rune {
	if p.charNames == nil {
		data := p.unicodeData()
		p.charNames = map[string]rune{}
		for _, interval := range data.Assigned {
			for c := interval[0]; c <= interval[1]; c++ {
				if canonicalName := runenames.Name(c); canonicalName != "" {
					p.charNames[canonicalName] = c
				}
			}
		}
		maps.Copy(p.charNames, data.Aliases)
	}
	c, present := p.charNames[strings.ToUpper(name)]
	if !present {
		p.bad = true
	}
	return c
}

func patternASCIIIdentifier(c rune, first bool) bool {
	return c == '_' || c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || !first && c >= '0' && c <= '9'
}
