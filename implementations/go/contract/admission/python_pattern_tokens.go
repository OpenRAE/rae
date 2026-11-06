package admission

import "strconv"

const (
	patternLiteral  = -1
	patternCategory = -2
	patternAnchor   = -3
)

func (p *pythonPattern) escape(inClass bool) (rune, int) {
	c := p.peek()
	if c < 0 {
		p.bad = true
		return 0, patternLiteral
	}
	p.pos++
	switch c {
	case 'd', 'D', 's', 'S', 'w', 'W':
		return 0, patternCategory
	case 'b', 'A', 'B', 'Z', 'z':
		return p.anchorEscape(c, inClass)
	case 'a':
		return '\a', patternLiteral
	case 'f':
		return '\f', patternLiteral
	case 'n':
		return '\n', patternLiteral
	case 'r':
		return '\r', patternLiteral
	case 't':
		return '\t', patternLiteral
	case 'v':
		return '\v', patternLiteral
	case 'x', 'u', 'U':
		length := map[rune]int{'x': 2, 'u': 4, 'U': 8}[c]
		return p.hexCharacter(length), patternLiteral
	case 'N':
		if !p.consume('{') {
			p.bad = true
			return 0, patternLiteral
		}
		return p.namedCharacter(p.until('}')), patternLiteral
	default:
		if c >= '0' && c <= '9' {
			return p.numericEscape(c, inClass)
		}
		if c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' {
			p.bad = true
		}
		return c, patternLiteral
	}
}

func (p *pythonPattern) anchorEscape(c rune, inClass bool) (rune, int) {
	if !inClass {
		return 0, patternAnchor
	}
	if c == 'b' {
		return '\b', patternLiteral
	}
	p.bad = true
	return 0, patternAnchor
}

func (p *pythonPattern) hexCharacter(length int) rune {
	if len(p.text)-p.pos < length {
		p.bad = true
		return 0
	}
	text := string(p.text[p.pos : p.pos+length])
	p.pos += length
	value, err := strconv.ParseUint(text, 16, 32)
	if err != nil || value > 0x10ffff {
		p.bad = true
		return 0
	}
	return rune(value)
}

func (p *pythonPattern) numericEscape(first rune, inClass bool) (rune, int) {
	start := p.pos - 1
	octal := first == '0' || inClass || first <= '7' && p.pos+1 < len(p.text) && p.text[p.pos] >= '0' && p.text[p.pos] <= '7' && p.text[p.pos+1] >= '0' && p.text[p.pos+1] <= '7'
	if octal {
		for p.pos < len(p.text) && p.pos-start < 3 && p.peek() >= '0' && p.peek() <= '7' {
			p.pos++
		}
		value, err := strconv.ParseUint(string(p.text[start:p.pos]), 8, 8)
		if err != nil {
			p.bad = true
		}
		return rune(value), patternLiteral
	}
	if p.peek() >= '0' && p.peek() <= '9' {
		p.pos++
	}
	value, err := strconv.ParseUint(string(p.text[start:p.pos]), 10, 8)
	if err != nil {
		p.bad = true
	}
	return 0, int(value)
}

func (p *pythonPattern) repetition() (uint64, uint64, bool) {
	switch p.peek() {
	case '*':
		p.pos++
		return 0, patternInfinite, true
	case '+':
		p.pos++
		return 1, patternInfinite, true
	case '?':
		p.pos++
		return 0, 1, true
	case '{':
		return p.bracedRepetition()
	default:
		return 0, 0, false
	}
}

func (p *pythonPattern) decimalToken() string {
	start := p.pos
	for p.peek() >= '0' && p.peek() <= '9' {
		p.pos++
	}
	return string(p.text[start:p.pos])
}

func (p *pythonPattern) bracedRepetition() (uint64, uint64, bool) {
	start := p.pos
	p.pos++
	lowText := p.decimalToken()
	hasComma := p.consume(',')
	highText := lowText
	if hasComma {
		highText = p.decimalToken()
	}
	if lowText == "" && !hasComma || !p.consume('}') {
		p.pos = start
		return 0, 0, false
	}
	low, high := uint64(0), patternInfinite
	if lowText != "" {
		low = p.repeatBound(lowText)
	}
	if highText != "" {
		high = p.repeatBound(highText)
	}
	if low > high {
		p.bad = true
	}
	return low, high, true
}

func (p *pythonPattern) repeatBound(text string) uint64 {
	value, err := strconv.ParseUint(text, 10, 32)
	if err != nil || value == 1<<32-1 {
		p.bad = true
	}
	return value
}
