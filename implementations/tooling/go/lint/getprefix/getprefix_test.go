package getprefix_test

import (
	"testing"

	"golang.org/x/tools/go/analysis/analysistest"

	"github.com/OpenRAE/rae/implementations/tooling/go/lint/getprefix"
)

func TestAnalyzer(t *testing.T) {
	analysistest.Run(t, analysistest.TestData(), getprefix.Analyzer, "a")
}
