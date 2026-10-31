// Package getprefix reports function and method names that start with a Get
// prefix.
//
// The Google Go style best practices say that function and method names do not
// use a Get or get prefix: a getter is named for the value that it returns. A
// method named only Get, such as a lookup by key, is not reported.
package getprefix

import (
	"go/ast"
	"strings"
	"unicode"
	"unicode/utf8"

	"golang.org/x/tools/go/analysis"
	"golang.org/x/tools/go/ast/inspector"
)

// Analyzer reports a function or method whose name is Get or get followed by a
// capitalized word.
var Analyzer = &analysis.Analyzer{
	Name: "getprefix",
	Doc:  "report function and method names that start with a Get prefix",
	URL:  "https://google.github.io/styleguide/go/best-practices#naming-conventions",
	Run:  run,
}

func run(pass *analysis.Pass) (any, error) {
	inspector.New(pass.Files).Preorder([]ast.Node{(*ast.FuncDecl)(nil)}, func(node ast.Node) {
		decl, ok := node.(*ast.FuncDecl)
		if ok && hasGetPrefix(decl.Name.Name) {
			pass.Reportf(decl.Name.Pos(), "function name %s has a Get prefix; name it for the value it returns", decl.Name.Name)
		}
	})
	return nil, nil
}

func hasGetPrefix(name string) bool {
	rest, ok := strings.CutPrefix(name, "Get")
	if !ok {
		rest, ok = strings.CutPrefix(name, "get")
	}
	first, _ := utf8.DecodeRuneInString(rest)
	return ok && unicode.IsUpper(first)
}
