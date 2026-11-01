package wrapverb_test

import (
	"testing"

	"golang.org/x/tools/go/analysis/analysistest"

	"github.com/OpenRAE/rae/implementations/tooling/go/lint/wrapverb"
)

func TestAnalyzer(t *testing.T) {
	analysistest.Run(t, analysistest.TestData(), wrapverb.Analyzer, "a")
}
