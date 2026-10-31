// Command archcheck checks the repository's Go code against the architecture
// model in implementations/architecture.json (ADR-122).
//
// Run it from the repository root. With -design, it checks only the model:
// the design step runs it after a change declares its new or changed packages
// in the model and before the change writes their code. Without -design, it
// also checks the code and the rule table of ADR-122.
//
//	archcheck [-design]
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"slices"

	"github.com/OpenRAE/rae/implementations/tooling/go/arch"
)

// The repository paths of the model and of the ADR that states the rules.
const (
	modelPath = "implementations/architecture.json"
	rulesPath = "docs/decisions/adrs/adr-122-go-architecture-model.md"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	status := run(ctx, os.Args[1:], os.Stdout, os.Stderr)
	stop()
	os.Exit(status)
}

// run executes the command in the working directory and returns its exit
// status. A failed write to the output streams has no recovery path, so the
// exit status alone reports it.
func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("archcheck", flag.ContinueOnError)
	flags.SetOutput(stderr)
	design := flags.Bool("design", false, "check only the model, before the code exists")
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 {
		return 2
	}
	findings, err := check(ctx, *design)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "archcheck: %v\n", err)
		return 1
	}
	for _, finding := range findings {
		_, _ = fmt.Fprintf(stderr, "archcheck: %s\n", finding)
	}
	if len(findings) > 0 {
		return 1
	}
	_, _ = fmt.Fprintln(stdout, "archcheck: no findings")
	return 0
}

// check returns the findings of the model, and also those of the code and the
// rule table unless design is set.
func check(ctx context.Context, design bool) ([]arch.Finding, error) {
	repo := os.DirFS(".")
	model, err := arch.Load(repo, modelPath)
	if err != nil {
		return nil, err
	}
	if findings := model.CheckDesign(); design || len(findings) > 0 {
		return findings, nil
	}
	ruleFindings, err := arch.CheckRules(repo, rulesPath)
	if err != nil {
		return nil, err
	}
	code, err := arch.LoadCode(ctx, ".", model)
	if err != nil {
		return nil, err
	}
	return slices.Concat(ruleFindings, model.CheckCode(code)), nil
}
