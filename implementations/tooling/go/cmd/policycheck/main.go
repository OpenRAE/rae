// Command policycheck runs the native Go repository governance checks.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/tooling/go/governance"
)

const prBodyTool = "pr-body"

func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }

func run(args []string, stdout, stderr io.Writer) int {
	request, asJSON, err := parseRequest(args, stderr)
	if err != nil {
		_, _ = fmt.Fprintln(stderr, "policycheck:", err)
		return 2
	}
	report, err := governance.Check(context.Background(), request)
	if err != nil {
		if _, known := fault.CategoryOf(err); known {
			_, _ = fmt.Fprintln(stderr, "policycheck:", err)
			return 1
		}
		_, _ = fmt.Fprintln(stderr, "policycheck: policy could not be evaluated")
		return 70
	}
	if err := renderReport(request, report, asJSON, stdout, stderr); err != nil {
		if request.Tool == prBodyTool {
			return 2
		}
		return 1
	}
	return report.ExitCode
}

func parseRequest(args []string, stderr io.Writer) (governance.Request, bool, error) {
	flags := flag.NewFlagSet("policycheck", flag.ContinueOnError)
	flags.SetOutput(stderr)
	request := governance.Request{}
	requestFlags(flags, &request)
	branch := flags.String("branch", "", "exact workflow branch for detached checkouts")
	reportOnly := flags.Bool("report", false, "render a non-gating inventory")
	audit := flags.Bool("report-open-closing-issues", false, "render the read-only closing issue audit")
	asJSON := flags.Bool("json", false, "emit reference findings as JSON")
	if err := flags.Parse(args); err != nil {
		return request, false, err
	}
	explicit := map[string]bool{}
	flags.Visit(func(option *flag.Flag) { explicit[option.Name] = true })
	request.BaseRevisionSet = explicit["base-rev"]
	normalizeExplicitPaths(&request, explicit)
	if explicit["branch"] {
		request.Branch = branch
	}
	if flags.NArg() > 0 {
		request.Paths = flags.Args()
		if request.Tool == "repo-policy" {
			for i, name := range request.Paths {
				request.Paths[i] = repoCLIPath(name)
			}
		}
	}
	if *reportOnly {
		request.Mode = governance.Inventory
	}
	if *audit {
		request.Mode = governance.ClosingAudit
	}
	err := prepareRequest(&request, explicit)
	return request, *asJSON, err
}

func requestFlags(flags *flag.FlagSet, request *governance.Request) {
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
	flags.BoolVar(&request.VerifyRemote, "verify-remote", false, "verify locked vocabulary source artifacts")
	flags.StringVar(&request.LocalInput, "local-input", "", "explicit locked vocabulary source artifact")
	flags.StringVar(&request.ActivityStreamsLocalInput, "activitystreams-local-input", "", "explicit locked ActivityStreams artifact")
	flags.StringVar(&request.FIPALocalInput, "fipa-local-input", "", "explicit locked FIPA artifact")
}

func prepareRequest(request *governance.Request, explicit map[string]bool) error {
	if request.Tool == "" {
		return errors.New("--tool is required")
	}
	if request.Tool == "repo-policy" {
		if request.CheckSet != "full" && request.CheckSet != "file-local" {
			return errors.New("--check-set must be full or file-local")
		}
		if explicit["base-rev"] && !regexp.MustCompile(`^[A-Za-z0-9_][A-Za-z0-9_./@^~{}-]*$`).MatchString(request.BaseRevision) {
			return errors.New("invalid base revision")
		}
	}
	if !request.VerifyRemote && (request.LocalInput != "" || request.ActivityStreamsLocalInput != "" || request.FIPALocalInput != "") {
		return errors.New("local vocabulary inputs require --verify-remote")
	}
	if request.Tool == prBodyTool && request.EventPath == "" && os.Getenv("GITHUB_EVENT_PATH") == "" {
		return errors.New("GITHUB_EVENT_PATH or --event-path is required")
	}
	if request.Tool == "pr-title" {
		return prepareTitle(request, explicit["title"])
	}
	return nil
}

func repoCLIPath(name string) string {
	prefix := ""
	if strings.HasPrefix(name, "//") && !strings.HasPrefix(name, "///") {
		prefix = "//"
	} else if strings.HasPrefix(name, "/") {
		prefix = "/"
	}
	parts := []string{}
	for part := range strings.SplitSeq(name, "/") {
		if part != "" && part != "." {
			parts = append(parts, part)
		}
	}
	if len(parts) == 0 && prefix == "" {
		return "."
	}
	return prefix + strings.Join(parts, "/")
}

func prepareTitle(request *governance.Request, explicit bool) error {
	if explicit {
		request.EventPath = ""
		return nil
	}
	if request.EventPath == "" {
		request.EventPath = os.Getenv("GITHUB_EVENT_PATH")
	}
	if request.EventPath != "" {
		return nil
	}
	title, exists := os.LookupEnv("PR_TITLE")
	if !exists {
		return errors.New("could not resolve a PR title to validate")
	}
	request.Title, request.Body = title, os.Getenv("PR_BODY")
	return nil
}

func renderReport(request governance.Request, report governance.Report, asJSON bool, stdout, stderr io.Writer) error {
	if report.Text != "" {
		_, err := io.WriteString(stdout, report.Text)
		return err
	}
	if asJSON {
		return json.NewEncoder(stdout).Encode(report.Findings)
	}
	if request.Tool == prBodyTool {
		return renderPRBody(request, report, stdout, stderr)
	}
	for _, finding := range report.Findings {
		path := ""
		if finding.Path != nil {
			path = *finding.Path + ": "
		}
		if _, err := fmt.Fprintf(stderr, "- [%s] %s%s\n", finding.RuleID, path, finding.Message); err != nil {
			return err
		}
	}
	if report.ExitCode == 0 && request.Mode == governance.Evaluate {
		_, err := fmt.Fprintf(stdout, "%s: OK\n", request.Tool)
		return err
	}
	return nil
}

func renderPRBody(request governance.Request, report governance.Report, stdout, stderr io.Writer) error {
	if report.ExitCode == 2 {
		_, err := fmt.Fprintln(stderr, "pr-body-guard: configuration error:", report.Findings[0].Message)
		return err
	}
	if report.ExitCode == 0 {
		if request.Mode == governance.ClosingAudit {
			return nil
		}
		_, err := fmt.Fprintln(stdout, "pr-body-guard: OK")
		return err
	}
	if _, err := fmt.Fprintln(stderr, "pr-body-guard: rejected pull request body"); err != nil {
		return err
	}
	for _, finding := range report.Findings {
		if _, err := fmt.Fprintf(stderr, "- [%s] %s\n", finding.RuleID, finding.Message); err != nil {
			return err
		}
	}
	return nil
}

// argparse's Path("") is '.', an explicit local object rather than omission.
func normalizeExplicitPaths(request *governance.Request, explicit map[string]bool) {
	for name, value := range map[string]*string{
		"output":                      &request.OutputRoot,
		"local-input":                 &request.LocalInput,
		"activitystreams-local-input": &request.ActivityStreamsLocalInput,
		"fipa-local-input":            &request.FIPALocalInput,
	} {
		if explicit[name] && *value == "" {
			*value = "."
		}
	}
}
