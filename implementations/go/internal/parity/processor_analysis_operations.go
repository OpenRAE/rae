package parity

import (
	"context"
	"encoding/json"
	"os"
	"path"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/processor/analysis"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func processorAnalysisRunner(kind string) Runner {
	return func(ctx context.Context, c Case) (json.RawMessage, error) {
		request, valid, err := processorAnalysisRequest(kind, c)
		if err != nil {
			return nil, err
		}
		if !valid {
			return formatEnvelope(2, nil)
		}
		result, err := analysis.AnalyzeContext(ctx, request)
		if err != nil {
			if category, known := fault.CategoryOf(err); known && (category == fault.InvalidInput || category == fault.Operational || category == fault.EvidenceIntegrity) {
				return formatEnvelope(1, nil)
			}
			return nil, err
		}
		code := 0
		if result.Document["outcome"] == "unsupported" {
			code = 2
		}
		stripAnalysisMessages(result.Document)
		return formatEnvelope(code, result.Document)
	}
}

const (
	processorCommand = "processor"
	profileField     = "profile"
)

func processorAnalysisRequest(kind string, c Case) (analysis.Request, bool, error) {
	if len(c.Args) < 3 || c.Args[0] != processorCommand || c.Args[1] != kind || strings.HasPrefix(c.Args[2], "-") {
		return analysis.Request{}, false, nil
	}
	name := c.Args[2]
	raw, ok := c.Files[name]
	if !ok {
		return analysis.Request{}, false, nil
	}
	request := analysis.Request{Kind: kind}
	for index := 3; index < len(c.Args); index += 2 {
		if index+1 >= len(c.Args) || c.Args[index] != "--profile" {
			return analysis.Request{}, false, nil
		}
		request.Options = map[string]any{profileField: c.Args[index+1]}
	}
	if kind == "satisfiability" {
		options := sdl.DefaultParseOptions()
		options.MigrationPolicy = sdl.AcceptMigration
		request.Source = &analysis.SourceInput{Source: sdl.SourceContext{Root: name, Sources: c.Files, RootBytes: raw}, Options: options}
		solver, err := analysis.OpenSolver(os.Getenv("RAES_TEST_Z3"))
		if err != nil {
			return analysis.Request{}, false, err
		}
		request.Solver = solver
	} else {
		request.Input = &analysis.JSONInput{SourceID: path.Base(name), Data: raw}
	}

	return request, true, nil
}

func stripAnalysisMessages(document map[string]any) {
	// The reference recorder removes human text only at the evidence's diagnostics field.
	diagnostics, _ := document["diagnostics"].([]any)
	for _, row := range diagnostics {
		if diagnostic, ok := row.(map[string]any); ok {
			delete(diagnostic, "message")
		}
	}
}
