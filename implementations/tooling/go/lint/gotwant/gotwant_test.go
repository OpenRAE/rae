package gotwant_test

import (
	"testing"

	"golang.org/x/tools/go/analysis/analysistest"

	"github.com/OpenRAE/rae/implementations/tooling/go/lint/gotwant"
)

func TestAnalyzer(t *testing.T) {
	analysistest.Run(t, analysistest.TestData(), gotwant.Analyzer, "a")
}
