// Package wrapverb reports fmt.Errorf calls that place the %w verb in the
// middle of the error format.
//
// The Google Go style best practices place %w at the end of an error format, so
// that the printed chain reads from newest to oldest. A sentinel error can go
// at the start instead. Both positions are accepted.
package wrapverb

import (
	"go/ast"
	"go/constant"
	"go/types"
	"strings"

	"golang.org/x/tools/go/analysis"
	"golang.org/x/tools/go/ast/inspector"
	"golang.org/x/tools/go/types/typeutil"
)

// Analyzer reports a fmt.Errorf format with a %w verb that is neither its first
// nor its last element.
var Analyzer = &analysis.Analyzer{
	Name: "wrapverb",
	Doc:  "report fmt.Errorf formats that place %w in the middle",
	URL:  "https://google.github.io/styleguide/go/best-practices#placement-of-w-in-errors",
	Run:  run,
}

func run(pass *analysis.Pass) (any, error) {
	inspector.New(pass.Files).Preorder([]ast.Node{(*ast.CallExpr)(nil)}, func(node ast.Node) {
		call, ok := node.(*ast.CallExpr)
		if !ok || len(call.Args) == 0 || !isErrorf(pass, call) {
			return
		}
		format := pass.TypesInfo.Types[call.Args[0]].Value
		if format == nil || format.Kind() != constant.String {
			return
		}
		if wrapsInMiddle(constant.StringVal(format)) {
			pass.Reportf(call.Args[0].Pos(), "place %%w at the start or the end of the error format")
		}
	})
	return nil, nil
}

func isErrorf(pass *analysis.Pass, call *ast.CallExpr) bool {
	fn, ok := typeutil.Callee(pass.TypesInfo, call).(*types.Func)
	return ok && fn.Pkg() != nil && fn.Pkg().Path() == "fmt" && fn.Name() == "Errorf"
}

// wrapsInMiddle reports whether a %w verb in format is neither at its start nor at its end.
func wrapsInMiddle(format string) bool {
	for i := 0; i < len(format); i++ {
		if format[i] != '%' {
			continue
		}
		end := verbEnd(format, i+1)
		if end > len(format) {
			return false
		}
		if format[end-1] == 'w' && i != 0 && end != len(format) {
			return true
		}
		i = end - 1
	}
	return false
}

// verbEnd returns the index just after the verb that begins at start, which
// follows a percent sign. A doubled percent sign is its own verb.
func verbEnd(format string, start int) int {
	end := start + strings.IndexFunc(format[start:], func(r rune) bool {
		return !strings.ContainsRune("+-# 0123456789.*[]", r)
	})
	if end < start {
		return len(format) + 1
	}
	return end + 1
}
