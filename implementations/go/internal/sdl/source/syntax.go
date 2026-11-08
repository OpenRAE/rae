package source

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"math"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/goccy/go-yaml/scanner"
	"github.com/goccy/go-yaml/token"
	"go.yaml.in/yaml/v3"
)

func tokenRange(t *token.Token) Range {
	if t == nil {
		return startRange()
	}
	start := Position{t.Position.Line, t.Position.Column}
	text := strings.TrimSpace(t.Origin)
	// A token origin includes presentation whitespace. Its position already
	// points to the token, so never count leading indentation in its extent.
	end := start
	for _, c := range text {
		if c == '\n' {
			end.Line++
			end.Column = 1
		} else {
			end.Column++
		}
	}
	return Range{start, end}
}
func scalarToken(t *token.Token) bool {
	return t.Type == token.StringType || t.Type == token.IntegerType || t.Type == token.FloatType || t.Type == token.NullType || t.Type == token.BoolType || t.Type == token.SingleQuoteType || t.Type == token.DoubleQuoteType || t.Type == token.BinaryIntegerType || t.Type == token.OctetIntegerType || t.Type == token.HexIntegerType || t.Type == token.InfinityType || t.Type == token.NanType || t.Type == token.MergeKeyType
}

type preflight struct {
	options                Options
	layout                 sourceLayout
	aliases, flow, scalars int
	indents                []int
	line                   int
	skipName               bool
	limitAlias             *token.Token
}

func scan(data []byte, options Options) (token.Tokens, error) {
	if !printableSource(data) {
		return nil, &parseError{}
	}
	var scannerState scanner.Scanner
	scannerState.Init(string(data))
	state := preflight{options: options, layout: newLayout(data)}
	var result token.Tokens
	for {
		batch, err := scannerState.Scan()
		if errors.Is(err, io.EOF) {
			break
		}
		for _, t := range batch {
			if tokenErr := state.token(t, data); tokenErr != nil {
				return nil, tokenErr
			}
			result.Add(t)
		}
		if err != nil {
			return nil, failure(parseCode, startRange(), options)
		}
	}
	if state.flow > 0 {
		end := endPosition(data)
		return nil, failure(parseCode, Range{end, end}, options)
	}
	return result, nil
}
func (p *preflight) token(t *token.Token, data []byte) error {
	if t.Type == token.SingleQuoteType || t.Type == token.DoubleQuoteType {
		if raw := p.layout.quoteOrigin(t); raw != "" {
			t.Origin = raw
		}
	}
	if err := p.presentation(t, data); err != nil {
		return err
	}
	if err := p.nesting(t); err != nil {
		return err
	}
	if t.Type == token.DoubleQuoteType {
		if span, ok := quotedSurrogate(t); ok {
			return failure("sdl.utf8", span, p.options)
		}
	}
	return p.value(t)
}

func (p *preflight) nesting(t *token.Token) error {
	if p.flow == 0 && t.Type != token.CommentType && (t.Position.Line != p.line || t.Type == token.SequenceEntryType) {
		p.indentation(t)
	}
	if t.Type == token.SequenceStartType || t.Type == token.MappingStartType {
		p.flow++
	}
	if t.Type == token.SequenceEndType || t.Type == token.MappingEndType {
		p.flow--
	}
	if p.flow+len(p.indents)-1 > p.options.Limits.MaxDepth {
		return failure(sourceLimitCode, tokenRange(t), p.options)
	}
	return nil
}

// Scanner IndentLevel decrements only once on any dedent. Track active
// indentation columns so sibling subtrees cannot accumulate fictitious depth.
func (p *preflight) indentation(t *token.Token) {
	indent := t.Position.IndentNum
	if t.Type == token.SequenceEntryType {
		indent = t.Position.Column - 1
	}
	for len(p.indents) > 0 && p.indents[len(p.indents)-1] > indent {
		p.indents = p.indents[:len(p.indents)-1]
	}
	if len(p.indents) == 0 || p.indents[len(p.indents)-1] < indent {
		p.indents = append(p.indents, indent)
	}
	p.line = t.Position.Line
}
func (p *preflight) presentation(t *token.Token, data []byte) error {
	r := tokenRange(t)
	if t.Type == token.InvalidType {
		if invalid, ok := surrogateRange(data, t); ok {
			return failure("sdl.utf8", invalid, p.options)
		}
		if strings.Contains(t.Error, "could not find end") {
			r.Start = endPosition(data)
		}
		return failure(parseCode, Range{r.Start, r.Start}, p.options)
	}
	if t.Type == token.TagType {
		return failure("sdl.explicit_tag", r, p.options)
	}
	if t.Type == token.DirectiveType {
		return failure("sdl.directive", directiveRange(data, r), p.options)
	}
	return nil
}
func (p *preflight) value(t *token.Token) error {
	if t.Type == token.AliasType {
		p.aliases++
		if p.aliases > p.options.Limits.MaxAliases {
			p.limitAlias = t
		}
	}
	if scalarToken(t) {
		if err := p.scalar(t); err != nil {
			return err
		}
		p.skipName = false
	}
	if t.Type == token.AnchorType || t.Type == token.AliasType {
		p.skipName = true
	}
	return nil
}
func (p *preflight) scalar(t *token.Token) error {
	r := tokenRange(t)
	if p.skipName {
		if p.limitAlias != nil {
			r.Start = tokenRange(p.limitAlias).Start
			return failure(sourceLimitCode, r, p.options)
		}
		return nil
	}
	p.scalars++
	if int64(len(t.Value)) > p.options.Limits.MaxScalarBytes || p.scalars > p.options.Limits.MaxNodes {
		return failure(sourceLimitCode, r, p.options)
	}
	return nil
}
func directiveRange(data []byte, r Range) Range {
	lines := strings.Split(string(data), "\n")
	if r.Start.Line <= len(lines) {
		r.End = Position{r.Start.Line, utf8.RuneCountInString(strings.TrimRight(lines[r.Start.Line-1], "\r")) + 1}
	}
	return r
}

type syntax struct {
	data       []byte
	options    Options
	anchors    map[string]bool
	cache      map[*yaml.Node]*node
	tokens     token.Tokens
	created    int
	lines      []string
	flowEnds   map[*token.Token]Position
	rawScalars bool
}

func compose(tokens token.Tokens, data []byte, options Options) (*node, error) {
	return composeSyntax(tokens, data, options, false)
}

func composeSyntax(tokens token.Tokens, data []byte, options Options, rawScalars bool) (*node, error) {
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	var document yaml.Node
	if err := decoder.Decode(&document); err != nil {
		if errors.Is(err, io.EOF) {
			return nil, &parseError{}
		}
		return nil, grammarError(err, tokens, data, options)
	}
	var next yaml.Node
	if err := decoder.Decode(&next); !errors.Is(err, io.EOF) {
		if err != nil {
			return nil, grammarError(err, tokens, data, options)
		}
		pos := Position{next.Line, next.Column}
		return nil, failure(parseCode, Range{pos, pos}, options)
	}
	if len(document.Content) == 0 {
		return nil, &parseError{}
	}
	state := syntax{data: data, options: options, anchors: map[string]bool{}, cache: map[*yaml.Node]*node{}, tokens: tokens, lines: strings.Split(string(data), "\n"), flowEnds: flowEndMarks(tokens), rawScalars: rawScalars}
	return state.build(document.Content[0])
}

func grammarError(err error, tokens token.Tokens, data []byte, options Options) error {
	line := 1
	text := err.Error()
	if _, after, ok := strings.Cut(text, "line "); ok {
		_, _ = fmt.Sscanf(after, "%d:", &line)
	}
	pos := Position{line, 1}
	for _, t := range tokens {
		if t.Position.Line == line {
			pos = Position{line, t.Position.Column}
			if t.Type == token.MappingValueType {
				break
			}
		}
	}
	if strings.Contains(text, "unknown anchor") {
		pos = unknownAnchorPosition(text, tokens, pos)
	}
	if strings.Contains(text, "end of stream") || strings.Contains(text, "expected node content") {
		pos = endPosition(data)
	}
	return failure(parseCode, Range{pos, pos}, options)
}

func unknownAnchorPosition(message string, tokens token.Tokens, fallback Position) Position {
	for _, t := range tokens {
		if t.Type == token.AliasType && t.Next != nil && strings.HasSuffix(message, "unknown anchor '"+t.Next.Value+"' referenced") {
			return Position{t.Position.Line, t.Position.Column}
		}
	}
	return fallback
}

func (s *syntax) build(n *yaml.Node) (*node, error) {
	if n.Kind == yaml.AliasNode {
		return s.build(n.Alias)
	}
	if previous, ok := s.cache[n]; ok {
		return previous, nil
	}
	span := Range{Position{n.Line, n.Column}, Position{n.Line, n.Column}}
	if n.Style&yaml.TaggedStyle != 0 {
		return nil, failure("sdl.explicit_tag", span, s.options)
	}
	if n.Anchor != "" {
		if s.anchors[n.Anchor] {
			return nil, failure(parseCode, span, s.options)
		}
		s.anchors[n.Anchor] = true
	}
	s.created++
	if s.created > s.options.Limits.MaxNodes {
		if n.Kind == yaml.ScalarNode {
			span.End = s.scalarEnd(n)
		}
		return nil, failure(sourceLimitCode, span, s.options)
	}
	result := &node{span: span}
	s.cache[n] = result
	if err := s.fill(n, result); err != nil {
		return nil, err
	}
	return result, nil
}
func (s *syntax) fill(n *yaml.Node, result *node) error {
	switch n.Kind {
	case yaml.MappingNode:
		return s.mapping(n, result)
	case yaml.SequenceNode:
		return s.sequence(n, result)
	case yaml.ScalarNode:
		result.kind = 'v'
		result.spelling = n.Value
		quoted := n.Style&(yaml.SingleQuotedStyle|yaml.DoubleQuotedStyle|yaml.LiteralStyle|yaml.FoldedStyle) != 0
		result.quoted = quoted
		result.merge = n.Value == "<<" && !quoted
		result.span.End = s.scalarEnd(n)
		if s.rawScalars {
			result.value = n.Value
			return nil
		}
		value, err := resolve(n.Value, quoted, result.span, s.options)
		if err != nil {
			return err
		}
		result.value = value
		return nil
	case yaml.DocumentNode, yaml.AliasNode:
		return failure(parseCode, result.span, s.options)
	default:
		return failure(parseCode, result.span, s.options)
	}
}
func (s *syntax) mapping(n *yaml.Node, result *node) error {
	result.kind = 'm'
	for i := 0; i < len(n.Content); i += 2 {
		key, err := s.build(n.Content[i])
		if err != nil {
			return err
		}
		value, err := s.build(n.Content[i+1])
		if err != nil {
			return err
		}
		result.entries = append(result.entries, member{key: key, value: value})
	}
	result.span.End = s.collectionEnd(n, result)
	return nil
}
func (s *syntax) sequence(n *yaml.Node, result *node) error {
	result.kind = 's'
	for _, c := range n.Content {
		child, err := s.build(c)
		if err != nil {
			return err
		}
		result.children = append(result.children, child)
	}
	result.span.End = s.collectionEnd(n, result)
	return nil
}

func (s *syntax) scalarEnd(n *yaml.Node) Position {
	start := Position{n.Line, n.Column}
	if n.Value == "" && n.Style == 0 {
		return s.implicitEnd(n, start)
	}
	index, _ := slices.BinarySearchFunc(s.tokens, start, compareTokenPosition)
	for _, t := range s.tokens[index:] {
		if decoration(t) {
			continue
		}
		if (t.Type == token.LiteralType || t.Type == token.FoldedType) && t.Next != nil {
			return Position{t.Position.Line + 1 + strings.Count(t.Next.Origin, "\n"), 1}
		}
		if scalarToken(t) {
			return tokenRange(t).End
		}
		break
	}
	return start
}
func decoration(t *token.Token) bool {
	if t.Type == token.AnchorType || t.Type == token.TagType {
		return true
	}
	return t.Prev != nil && (t.Prev.Type == token.AnchorType || t.Prev.Type == token.TagType)
}
func (s *syntax) collectionEnd(n *yaml.Node, result *node) Position {
	if n.Style&yaml.FlowStyle != 0 {
		return s.flowEnd(result.span.Start)
	}
	last := result.span.End
	for _, child := range n.Content {
		end := s.presentationEnd(child)
		if before(last, end) {
			last = end
		}
	}
	return s.blockEnd(result.span.Start, last)
}
func (s *syntax) flowEnd(start Position) Position {
	index, _ := slices.BinarySearchFunc(s.tokens, start, compareTokenPosition)
	for _, t := range s.tokens[index:] {
		if end, ok := s.flowEnds[t]; ok {
			return end
		}
	}
	return start
}
func (s *syntax) blockEnd(start, last Position) Position {
	for line := last.Line; line <= len(s.lines); line++ {
		text := s.lines[line-1]
		if line == last.Line && last.Column > 1 {
			continue
		}
		stripped := strings.TrimLeft(text, " \t\r")
		if stripped == "" || strings.HasPrefix(stripped, "#") {
			continue
		}
		indent := len(text) - len(stripped)
		if line > start.Line && indent < start.Column {
			return Position{line, indent + 1}
		}
	}
	return Position{len(s.lines), utf8.RuneCountInString(s.lines[len(s.lines)-1]) + 1}
}
func before(a, b Position) bool { return a.Line < b.Line || a.Line == b.Line && a.Column < b.Column }

type metric struct{ cost, height int }
type graphMetrics struct {
	nodes   int
	cache   map[*node]metric
	active  map[*node]bool
	options Options
}

func measure(root *node, options Options) error {
	g := &graphMetrics{cache: map[*node]metric{}, active: map[*node]bool{}, options: options}
	_, err := g.visit(root, 1)
	return err
}
func (g *graphMetrics) visit(n *node, depth int) (metric, error) {
	limit := func() error { return failure(sourceLimitCode, n.span, g.options) }
	if depth > g.options.Limits.MaxDepth {
		return metric{}, limit()
	}
	if g.active[n] {
		return metric{}, nil
	}
	if cached, ok := g.cache[n]; ok {
		if cached.height > g.options.Limits.MaxDepth-depth+1 {
			return metric{}, limit()
		}
		return cached, nil
	}
	g.nodes++
	if g.nodes > g.options.Limits.MaxNodes {
		return metric{}, limit()
	}

	g.active[n] = true
	m := metric{cost: 1, height: 1}
	for _, c := range children(n) {
		cm, err := g.visit(c, depth+1)
		if err != nil {
			return metric{}, err
		}
		if cm.cost > g.options.Limits.MaxExpandedNodes-m.cost {
			return metric{}, limit()
		}
		m.cost += cm.cost
		m.height = max(m.height, cm.height+1)
	}
	delete(g.active, n)
	g.cache[n] = m
	return m, nil
}
func children(n *node) []*node {
	if n.kind == 's' {
		return n.children
	}
	result := make([]*node, 0, len(n.entries)*2)
	for _, e := range n.entries {
		result = append(result, e.key, e.value)
	}
	return result
}
func construct(root *node, options Options) error {
	seen := map[*node]bool{}
	stack := []*node{root}
	for len(stack) > 0 {
		n := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if seen[n] {
			continue
		}
		seen[n] = true
		if f, ok := n.value.(float64); ok && (math.IsNaN(f) || math.IsInf(f, 0)) {
			return failure("sdl.non_json_value", startRange(), options)
		}
		stack = append(stack, children(n)...)
	}
	return nil
}

func endPosition(data []byte) Position {
	lines := strings.Split(string(data), "\n")
	return Position{len(lines), utf8.RuneCountInString(lines[len(lines)-1]) + 1}
}

// A YAML escape cannot denote a surrogate, including a surrogate pair.
func surrogateRange(data []byte, t *token.Token) (Range, bool) {
	runes := []rune(string(data))
	i := min(t.Position.Offset-1, len(runes)-1)
	for i >= 0 && runes[i] != '"' && runes[i] != '\n' {
		i--
	}
	if i < 0 || runes[i] != '"' {
		return Range{}, false
	}
	start := i
	for end := i + 1; end < len(runes); end++ {
		if runes[end] != '"' {
			continue
		}
		fake := *t
		fake.Origin = string(runes[start : end+1])
		fake.Position = &token.Position{Line: t.Position.Line, Column: t.Position.Column - 1}
		return quotedSurrogate(&fake)
	}
	return Range{}, false
}
func quotedSurrogate(t *token.Token) (Range, bool) {
	raw := []rune(strings.TrimSpace(t.Origin))
	for i := 0; i < len(raw); i++ {
		if raw[i] != '\\' || i+1 >= len(raw) {
			continue
		}
		count := escapeDigits(raw[i+1])
		if count == 0 {
			i++
			continue
		}
		if i+count+2 > len(raw) {
			break
		}
		if surrogateDigits(raw[i+2 : i+2+count]) {
			return tokenRange(t), true
		}
		i += count + 1
	}
	return Range{}, false
}
func escapeDigits(c rune) int {
	if c == 'u' {
		return 4
	}
	if c == 'U' {
		return 8
	}
	return 0
}
func surrogateDigits(raw []rune) bool {
	v, err := strconv.ParseUint(string(raw), 16, 32)
	return err == nil && v >= 0xD800 && v <= 0xDFFF
}

type sourceLayout struct {
	runes []rune
	lines []int
}

func newLayout(data []byte) sourceLayout {
	result := sourceLayout{runes: []rune(string(data)), lines: []int{0}}
	for i, c := range result.runes {
		if c == '\n' {
			result.lines = append(result.lines, i+1)
		}
	}
	return result
}
func (l sourceLayout) quoteOrigin(t *token.Token) string {
	if t.Position.Line < 1 || t.Position.Line > len(l.lines) {
		return ""
	}
	offset := l.lines[t.Position.Line-1] + t.Position.Column - 1
	runes := l.runes
	if offset >= len(runes) {
		return ""
	}
	quote := runes[offset]
	if quote != '"' && quote != '\'' {
		return ""
	}
	for i := offset + 1; i < len(runes); i++ {
		if quote == '"' && runes[i] == '\\' {
			i++
			continue
		}
		if runes[i] != quote {
			continue
		}
		if quote == '\'' && i+1 < len(runes) && runes[i+1] == quote {
			i++
			continue
		}
		return string(runes[offset : i+1])
	}
	return ""
}

func flowEndMarks(tokens token.Tokens) map[*token.Token]Position {
	result := map[*token.Token]Position{}
	var stack []*token.Token
	for _, t := range tokens {
		if t.Type == token.SequenceStartType || t.Type == token.MappingStartType {
			stack = append(stack, t)
		}
		if (t.Type == token.SequenceEndType || t.Type == token.MappingEndType) && len(stack) > 0 {
			start := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			result[start] = tokenRange(t).End
		}
	}
	return result
}

func compareTokenPosition(t *token.Token, p Position) int {
	mark := Position{t.Position.Line, t.Position.Column}
	if before(mark, p) {
		return -1
	}
	if before(p, mark) {
		return 1
	}
	return 0
}

func (s *syntax) presentationEnd(n *yaml.Node) Position {
	if n.Kind == yaml.AliasNode {
		return Position{n.Line, n.Column + utf8.RuneCountInString(n.Value) + 1}
	}
	if built, ok := s.cache[n]; ok {
		return built.span.End
	}
	return Position{n.Line, n.Column}
}

func printableSource(data []byte) bool {
	for _, c := range string(data) {
		allowed := c == '\t' || c == '\n' || c == '\r' || c >= 0x20 && c <= 0x7e || c == 0x85 || c >= 0xa0 && c <= 0xd7ff || c >= 0xe000 && c <= 0xfffd || c >= 0x10000 && c <= 0x10ffff
		if !allowed {
			return false
		}
	}
	return true
}

func (s *syntax) implicitEnd(n *yaml.Node, start Position) Position {
	if n.Anchor != "" {
		index, found := slices.BinarySearchFunc(s.tokens, start, compareTokenPosition)
		if found && index+1 < len(s.tokens) {
			return tokenRange(s.tokens[index+1]).End
		}
	}
	return start
}
