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
	"regexp"

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

// verb matches one fmt verb: a percent sign, then flags, argument indexes,
// width, and precision, and then the verb character. A doubled percent sign is
// a verb too.
var verb = regexp.MustCompile(`%[-+# 0-9.*\[\]]*[^-+# 0-9.*\[\]]`)

// wrapsInMiddle reports whether a %w verb in format is neither at its start nor at its end.
func wrapsInMiddle(format string) bool {
	for _, loc := range verb.FindAllStringIndex(format, -1) {
		if format[loc[1]-1] == 'w' && loc[0] != 0 && loc[1] != len(format) {
			return true
		}
	}
	return false
}
