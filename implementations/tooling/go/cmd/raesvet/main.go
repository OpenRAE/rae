// Command raesvet runs the repository's own go/analysis checks, the Google Go
// style rules that no linter in golangci-lint covers. Run it through go vet:
//
//	go vet -vettool=$(command -v raesvet) ./...
package main

import (
	"golang.org/x/tools/go/analysis/unitchecker"

	"github.com/OpenRAE/rae/implementations/tooling/go/lint/getprefix"
	"github.com/OpenRAE/rae/implementations/tooling/go/lint/gotwant"
	"github.com/OpenRAE/rae/implementations/tooling/go/lint/wrapverb"
)

func main() {
	unitchecker.Main(getprefix.Analyzer, gotwant.Analyzer, wrapverb.Analyzer)
}
