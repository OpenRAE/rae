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
	flags.StringVar(&request.CheckSet, "check-set", "full", "full or file-local repository checks")
	flags.StringVar(&request.OutputRoot, "output", "", "built documentation output")
	flags.StringVar(&request.EventPath, "event-path", "", "PR event JSON")
	flags.StringVar(&request.IssuesFile, "issues-file", "", "explicit local issue fixture")
	flags.StringVar(&request.SummaryFile, "summary-file", "", "read-only issue audit destination")
	flags.StringVar(&request.CommitMessagesFile, "commit-messages-file", "", "changelog-bound commit messages")
	flags.StringVar(&request.Title, "title", "", "explicit local PR title")
	flags.StringVar(&request.Body, "body", "", "explicit local PR body")
	flags.BoolVar(&request.RequireGovernance, "require-governance", false, "refuse unavailable governance")
	flags.BoolVar(&request.Staged, "staged", false, "inspect staged changes")
	reportOnly := flags.Bool("report", false, "render a non-gating inventory")
	audit := flags.Bool("report-open-closing-issues", false, "render the read-only closing issue audit")
	asJSON := flags.Bool("json", false, "emit reference findings as JSON")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	request.Paths = flags.Args()
	if *reportOnly {
		request.Mode = governance.Inventory
	}
	if *audit {
		request.Mode = governance.ClosingAudit
	}
	report, err := governance.Check(context.Background(), request)
	if err != nil {
		_, _ = fmt.Fprintln(stderr, "policycheck: policy could not be evaluated")
		return 1
	}
	if report.Text != "" {
		if _, err := io.WriteString(stdout, report.Text); err != nil {
			return 1
		}
	} else if *asJSON {
		if err := json.NewEncoder(stdout).Encode(report.Findings); err != nil {
			return 1
		}
	}
	return report.ExitCode
}
