// Command policycheck runs the native Go repository governance checks.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/OpenRAE/rae/implementations/tooling/go/governance"
)

func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }

func run(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("policycheck", flag.ContinueOnError)
	flags.SetOutput(stderr)
	request := governance.Request{}
	flags.StringVar(&request.Tool, "tool", "", "reference check name")
	flags.StringVar(&request.Root, "repo-root", ".", "repository root")
	flags.StringVar(&request.BaseRevision, "base-rev", "", "comparison revision")
	flags.StringVar(&request.RequirementUID, "requirement-uid", "", "requirement context")
	flags.BoolVar(&request.Staged, "staged", false, "inspect staged changes")
	asJSON := flags.Bool("json", false, "emit reference findings as JSON")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	request.Paths = flags.Args()
	report, err := governance.Check(context.Background(), request)
	if err != nil {
		_, _ = fmt.Fprintln(stderr, "policycheck: policy could not be evaluated")
		return 1
	}
	if *asJSON {
		if err := json.NewEncoder(stdout).Encode(report.Findings); err != nil {
			return 1
		}
	}
	if len(report.Findings) != 0 || report.Status == "required-unevaluated" {
		return 1
	}
	return 0
}
