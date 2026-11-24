package admission

import "math"

// This parser checks syntax only. In particular it never compiles or evaluates
// a caller-supplied backtracking expression. Widths establish Python's fixed
// lookbehind rule, including references to earlier closed capture groups.
type patternWidth struct{ low, high uint64 }

const patternInfinite = uint64(math.MaxUint64 / 2)

type pythonPattern struct {
	text       []rune
	pos, depth int
	bad        bool
	start      bool
	flags      uint8
	lookbehind int
	groups     []patternWidth
	closed     []bool
	names      map[string]int
	conditions []int
	unicode    *patternUnicode
	charNames  map[string]rune
	resolved   map[string]rune
}

func pythonPatternValid(source string) bool {
	_, err := ParsePythonPattern(source)
	return err == nil
}

func parsePythonPattern(source string) (PythonPatternSyntax, error) {
	p := pythonPattern{text: []rune(source), start: true, lookbehind: -1, groups: []patternWidth{{}}, closed: []bool{false}, names: map[string]int{}}
	p.expression(0)
	if p.pos != len(p.text) || p.flags&patternASCII != 0 && p.flags&patternUnicodeFlag != 0 {
		return PythonPatternSyntax{}, invalid()
	}
	for _, group := range p.conditions {
		if group <= 0 || group >= len(p.groups) {
			return PythonPatternSyntax{}, invalid()
		}
	}
	if p.bad {
		return PythonPatternSyntax{}, invalid()
	}
	return PythonPatternSyntax{characters: p.resolved}, nil
}

func patternAdd(a, b uint64) uint64 { return min(patternInfinite, a+min(b, patternInfinite)) }
func patternMultiply(a, b uint64) uint64 {
	if a == 0 || b == 0 {
		return 0
	}
	if a > patternInfinite/b {
		return patternInfinite
	}
	return a * b
}

func (p *pythonPattern) consume(c rune) bool {
	if p.pos < len(p.text) && p.text[p.pos] == c {
		p.pos++
		return true
	}
	return false
}

func (p *pythonPattern) peek() rune {
	if p.pos == len(p.text) {
		return -1
	}
	return p.text[p.pos]
}

func (p *pythonPattern) ignored() {
	for p.pos < len(p.text) {
		if p.pos+2 < len(p.text) && p.text[p.pos] == '(' && p.text[p.pos+1] == '?' && p.text[p.pos+2] == '#' {
			p.pos += 3
			p.comment(')')
			continue
		}
		if p.flags&patternVerbose == 0 {
			return
		}
		switch p.peek() {
		case ' ', '\t', '\n', '\r', '\v', '\f':
			p.pos++
		case '#':
			p.pos++
			p.comment('\n')
		default:
			return
		}
	}
}

func (p *pythonPattern) comment(end rune) {
	for p.pos < len(p.text) {
		if p.consume(end) {
			return
		}
		if p.consume('\\') && p.pos < len(p.text) {
			p.pos++
		} else if p.pos < len(p.text) {
			p.pos++
		}
	}
	if end == ')' {
		p.bad = true
	}
}

func (p *pythonPattern) expression(maxBranches int) patternWidth {
	p.depth++
	defer func() { p.depth-- }()
	if p.depth > 512 {
		p.bad = true
		return patternWidth{}
	}
	result := patternWidth{low: patternInfinite}
	for branches := 1; ; branches++ {
		current := p.sequence()
		result.low, result.high = min(result.low, current.low), max(result.high, current.high)
		if p.bad || !p.consume('|') {
			if maxBranches == 2 && branches == 1 {
				result.low = 0
			}
			return result
		}
		p.start = false
		if maxBranches > 0 && branches >= maxBranches {
			p.bad = true
			return result
		}
	}
}

func (p *pythonPattern) sequence() patternWidth {
	current := patternWidth{}
	for !p.bad {
		p.ignored()
		if p.peek() == -1 || p.peek() == ')' || p.peek() == '|' {
			break
		}
		width, repeatable, present := p.atom()
		if !present {
			continue
		}
		p.start = false
		p.ignored()
		width = p.repeatedWidth(width, repeatable)
		current = patternWidth{patternAdd(current.low, width.low), patternAdd(current.high, width.high)}
	}
	return current
}

func (p *pythonPattern) repeatedWidth(width patternWidth, repeatable bool) patternWidth {
	low, high, exists := p.repetition()
	if !exists {
		return width
	}
	if !repeatable {
		p.bad = true
	}
	if !p.consume('?') {
		p.consume('+')
	}
	return patternWidth{patternMultiply(width.low, low), patternMultiply(width.high, high)}
}

func (p *pythonPattern) atom() (patternWidth, bool, bool) {
	c := p.peek()
	p.pos++
	switch c {
	case '(':
		return p.group()
	case '[':
		p.characterClass()
		return patternWidth{1, 1}, true, true
	case '\\':
		_, category := p.escape(false)
		if category == patternAnchor {
			return patternWidth{}, false, true
		}
		if category > 0 {
			return p.reference(category), true, true
		}
	case '^', '$':
		return patternWidth{}, false, true
	case '*', '+', '?':
		p.bad = true
	case '{':
		p.pos--
		_, _, exists := p.repetition()
		if exists {
			p.bad = true
		} else {
			p.pos++
		}
	}
	return patternWidth{1, 1}, true, true
}

func (p *pythonPattern) reference(group int) patternWidth {
	if group <= 0 || group >= len(p.groups) || !p.closed[group] || p.lookbehind >= 0 && group >= p.lookbehind {
		p.bad = true
		return patternWidth{}
	}
	return p.groups[group]
}

func (p *pythonPattern) characterClass() {
	p.consume('^')
	first := true
	for !p.bad {
		if p.peek() == -1 {
			p.bad = true
			return
		}
		if !first && p.consume(']') {
			return
		}
		first = false
		left, leftKind := p.classCharacter()
		if p.consume('-') && p.peek() != ']' {
			right, rightKind := p.classCharacter()
			if leftKind != patternLiteral || rightKind != patternLiteral || left > right {
				p.bad = true
			}
		}
	}
}

func (p *pythonPattern) classCharacter() (rune, int) {
	if p.consume('\\') {
		return p.escape(true)
	}
	c := p.peek()
	if c < 0 {
		p.bad = true
		return 0, patternLiteral
	}
	p.pos++
	return c, patternLiteral
}
