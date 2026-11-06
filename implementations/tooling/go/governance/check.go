// Package governance checks repository policy against its existing authorities.
// It does not define policy or grant authority to candidate repository content.
package governance

import (
	"context"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
)

// Finding is a reference-tool finding. A nil Path is JSON null. Status is
// present only for the reference's explicitly unevaluated governance result.
type Finding struct {
	RuleID  string  `json:"rule_id"`
	Message string  `json:"message"`
	Path    *string `json:"path"`
	Status  string  `json:"status,omitempty"`
}

// Mode selects policy evaluation or one of the reference's read-only reports.
type Mode string

const (
	// Evaluate runs the selected policy gate.
	Evaluate Mode = ""
	// Inventory renders coverage or requirement ownership without gating.
	Inventory Mode = "report"
	// ClosingAudit inspects declared closing issues without modifying them.
	ClosingAudit Mode = "closing-audit"
)

// DocumentRead is an actual read recorded by the documentation builder.
// Page is the builder's document name; File is resolved against its source root.
type DocumentRead struct{ Page, File string }

// Documentation contains observations from the trusted builder, not claims
// extracted from a candidate document. ImportedModules contains actual imported
// source files; ModuleRoots restrict the existing documented-module exemption.
// The unchanged Sphinx guard remains enforced until the native builder lands.
type Documentation struct {
	SourceRoot      string
	Reads           []DocumentRead
	ImportedModules []string
	ModuleRoots     []string
}

// Request selects a check and its explicit inputs. Today is an ISO date; an
// empty value uses the injected Clock. PR text and event files are untrusted.
// IssuesFile is an explicit local fixture option and is never selected by an event.
type Request struct {
	Tool               string
	Root               string
	Paths              []string
	BaseRevision       string
	RequirementUID     string
	Today              string
	Clock              clock.Clock
	Mode               Mode
	CheckSet           string
	OutputRoot         string
	Documentation      *Documentation
	Body               string
	Title              string
	CommitMessages     string
	CommitMessagesFile string
	Repository         string
	EventPath          string
	IssuesFile         string
	SummaryFile        string
	RequireGovernance  bool
	Staged             bool
}

// Report retains reference finding order and distinguishes evaluation from
// unavailable optional governance. Text carries a reference read-only report;
// ExitCode preserves non-gating reports and the reference's configuration errors.
type Report struct {
	Findings []Finding
	Status   string
	Text     string
	ExitCode int
}

type checker struct{ request Request }

// Check evaluates one named policy. An unsupported check refuses evaluation;
// it must never be mistaken for a successful policy verdict.
func Check(ctx context.Context, request Request) (Report, error) {
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	if request.Today == "" {
		request.Today = clock.Read(request.Clock).Format("2006-01-02")
	}
	c := checker{request: request}
	return c.check(ctx)
}

func (c *checker) check(_ context.Context) (Report, error) {
	return Report{}, errors.New("governance check is not implemented")
}
