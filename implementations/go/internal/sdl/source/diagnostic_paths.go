package source

import (
	"cmp"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// A shared path stores each token once. Eager full pointers can multiply a
// long common prefix by every descendant, even for an otherwise bounded graph.
type sourcePath struct {
	parent   *sourcePath
	token    string
	depth    int
	children map[string]*sourcePath
}

func (p *sourcePath) child(token string) *sourcePath {
	if p.children == nil {
		p.children = map[string]*sourcePath{}
	}
	if child := p.children[token]; child != nil {
		return child
	}
	child := &sourcePath{parent: p, token: token, depth: p.depth + 1}
	p.children[token] = child
	return child
}
func rootPath(tokens []string) *sourcePath {
	root := &sourcePath{}
	for _, token := range tokens {
		root = root.child(token)
	}
	return root
}
func (p *sourcePath) pointer() string {
	tokens := make([]string, p.depth)
	for current := p; current.parent != nil; current = current.parent {
		tokens[current.depth-1] = current.token
	}
	return jsonpointer.FromTokens(tokens)
}
func comparePaths(left, right *sourcePath) int {
	if left == right {
		return 0
	}
	a, b := left, right
	for a.depth > b.depth {
		a = a.parent
	}
	for b.depth > a.depth {
		b = b.parent
	}
	for a != b {
		a = a.parent
		b = b.parent
	}
	common := a
	if common == left || common == right {
		return cmp.Compare(left.depth, right.depth)
	}
	firstLeft, firstRight := left, right
	for firstLeft.parent != common {
		firstLeft = firstLeft.parent
	}
	for firstRight.parent != common {
		firstRight = firstRight.parent
	}
	aText, bText := jsonpointer.EscapeToken(firstLeft.token), jsonpointer.EscapeToken(firstRight.token)
	if firstLeft != left {
		aText += "/"
	}
	if firstRight != right {
		bText += "/"
	}
	return strings.Compare(aText, bText)
}

type pendingDiagnostic struct {
	diagnostic Diagnostic
	path       *sourcePath
}
type diagnosticIdentity struct {
	code       string
	path       *sourcePath
	start      Position
	related    Range
	hasRelated bool
}

func materializeDiagnostics(rows []pendingDiagnostic) []Diagnostic {
	result := make([]Diagnostic, len(rows))
	for i, row := range rows {
		result[i] = row.diagnostic
		result[i].Pointer = row.path.pointer()
	}
	return copyDiagnostics(result)
}
