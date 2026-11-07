package governance

import (
	"context"
	"strings"

	ts "github.com/odvcencio/gotreesitter"
	"github.com/odvcencio/gotreesitter/grammars"
	"golang.org/x/text/unicode/norm"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type pythonLiteralSource struct {
	data  []byte
	lang  *ts.Language
	named admission.PythonPatternSyntax
}

const pythonComment = "comment"

func pythonLiteralAssignments(ctx context.Context, source string, names ...string) map[string]string {
	values := map[string]string{}
	data := []byte(source)
	tree, err := pythonSyntax(ctx, data)
	if err != nil {
		return values
	}
	defer tree.Release()
	lang := grammars.PythonLanguage()
	root := tree.RootNode()
	named, valid := pythonLiteralNames(root, data, lang)
	if !valid {
		return values
	}
	reader := pythonLiteralSource{data: data, lang: lang, named: named}
	for _, name := range names {
		for i := range root.NamedChildCount() {
			value, valid := reader.assignment(root.NamedChild(i), name)
			if valid {
				values[name] = value
				break
			}
		}
	}
	return values
}

func (p pythonLiteralSource) assignment(node *ts.Node, name string) (string, bool) {
	if node.Type(p.lang) == "expression_statement" {
		node = node.NamedChild(0)
	}
	selected := false
	for node != nil && node.Type(p.lang) == "assignment" {
		selected = selected || p.targetName(node.ChildByFieldName("left", p.lang)) == name
		node = node.ChildByFieldName("right", p.lang)
	}
	if !selected || node == nil {
		return "", false
	}
	return p.string(node)
}

func (p pythonLiteralSource) targetName(node *ts.Node) string {
	for node != nil && (node.Type(p.lang) == "tuple_pattern" || node.Type(p.lang) == pythonParentheses) {
		for i := range node.ChildCount() {
			if node.Child(i).Type(p.lang) == "," {
				return ""
			}
		}
		node = pythonSingleChild(node, p.lang)
	}
	if node != nil && node.Type(p.lang) == pythonIdentifier {
		return norm.NFKC.String(node.Text(p.data))
	}
	return ""
}

func pythonSingleChild(node *ts.Node, lang *ts.Language) *ts.Node {
	var result *ts.Node
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		if child.Type(lang) == pythonComment {
			continue
		}
		if result != nil {
			return nil
		}
		result = child
	}
	return result
}

func (p pythonLiteralSource) string(node *ts.Node) (string, bool) {
	switch node.Type(p.lang) {
	case pythonParentheses, "concatenated_string":
		var out strings.Builder
		for i := range node.NamedChildCount() {
			child := node.NamedChild(i)
			if child.Type(p.lang) == pythonComment {
				continue
			}
			part, valid := p.string(child)
			if !valid {
				return "", false
			}
			out.WriteString(part)
		}
		return out.String(), true
	case pythonStringNode:
		return pythonStringToken(node.Text(p.data), p.named)
	default:
		return "", false
	}
}

func pythonStringToken(source string, syntax admission.PythonPatternSyntax) (string, bool) {
	start := strings.IndexAny(source, "\"'")
	if start < 0 {
		return "", false
	}
	prefix := strings.ToLower(source[:start])
	if prefix != "" && prefix != "u" && prefix != "r" {
		return "", false
	}
	quote := source[start : start+1]
	if strings.HasPrefix(source[start:], strings.Repeat(quote, 3)) {
		quote = strings.Repeat(quote, 3)
	}
	if len(source) < start+2*len(quote) || !strings.HasSuffix(source, quote) {
		return "", false
	}
	body := source[start+len(quote) : len(source)-len(quote)]
	if prefix == "r" {
		return body, true
	}
	return pythonStringContentMode(body, false, syntax)
}
