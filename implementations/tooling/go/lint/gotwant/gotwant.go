// Package gotwant reports test failure messages that print the wanted value
// before the actual value.
//
// The Google Go style decisions require failure messages to print the actual
// value first ("got before want").
package gotwant

import (
	"go/ast"
	"go/constant"
	"go/types"
	"regexp"

	"golang.org/x/tools/go/analysis"
	"golang.org/x/tools/go/ast/inspector"
	"golang.org/x/tools/go/types/typeutil"
)

// Analyzer reports a failure message whose format names "want" before "got".
var Analyzer = &analysis.Analyzer{
	Name: "gotwant",
	Doc:  "report test failure messages that print want before got",
	URL:  "https://google.github.io/styleguide/go/decisions#got-before-want",
	Run:  run,
}

var (
	gotWord  = regexp.MustCompile(`\bgot\b`)
	wantWord = regexp.MustCompile(`\bwant\b`)
)

func run(pass *analysis.Pass) (any, error) {
	inspector.New(pass.Files).Preorder([]ast.Node{(*ast.CallExpr)(nil)}, func(node ast.Node) {
		call, ok := node.(*ast.CallExpr)
		if !ok || len(call.Args) == 0 || !isTestingFailure(pass, call) {
			return
		}
		format := pass.TypesInfo.Types[call.Args[0]].Value
		if format == nil || format.Kind() != constant.String {
			return
		}
		if wantsBeforeGot(constant.StringVal(format)) {
			pass.Reportf(call.Args[0].Pos(), "failure message prints want before got; print got first")
		}
	})
	return nil, nil
}

// isTestingFailure reports whether call is the Errorf or Fatalf method of a type in package testing.
func isTestingFailure(pass *analysis.Pass, call *ast.CallExpr) bool {
	method, ok := typeutil.Callee(pass.TypesInfo, call).(*types.Func)
	return ok && method.Pkg() != nil && method.Pkg().Path() == "testing" &&
		(method.Name() == "Errorf" || method.Name() == "Fatalf")
}

func wantsBeforeGot(format string) bool {
	got := gotWord.FindStringIndex(format)
	want := wantWord.FindStringIndex(format)
	return got != nil && want != nil && want[0] < got[0]
}
