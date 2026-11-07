// Package governance checks repository policy against its existing authorities.
// It does not define policy or grant authority to candidate repository content.
package governance

import (
	"context"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
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
	Tool         string
	Root         string
	Paths        []string
	BaseRevision string
	// BaseRevisionSet preserves an explicitly empty --base-rev for merge diffs.
	BaseRevisionSet bool
	// Branch overrides branch discovery, including an explicitly empty branch.
	Branch                    *string
	RequirementUID            string
	Today                     string
	Clock                     clock.Clock
	Mode                      Mode
	CheckSet                  string
	OutputRoot                string
	Documentation             *Documentation
	Body                      string
	Title                     string
	CommitMessages            string
	CommitMessagesFile        string
	Repository                string
	EventPath                 string
	IssuesFile                string
	SummaryFile               string
	RequireGovernance         bool
	Staged                    bool
	VerifyRemote              bool
	LocalInput                string
	ActivityStreamsLocalInput string
	FIPALocalInput            string
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

type checker struct {
	request   Request
	contracts *admission.Validator
}

// Check evaluates one named policy. An unsupported check refuses evaluation;
// it must never be mistaken for a successful policy verdict.
func Check(ctx context.Context, request Request) (Report, error) {
	return new(checker).evaluate(ctx, request)
}

func (c *checker) evaluate(ctx context.Context, request Request) (Report, error) {
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	if request.Today == "" {
		request.Today = clock.Read(request.Clock).Format("2006-01-02")
	}
	c.request = request
	report, err := c.check(ctx)
	if cancelled := ctx.Err(); cancelled != nil {
		return Report{}, cancelled
	}
	return report, classifyPolicyError(err)
}

func (c *checker) check(ctx context.Context) (Report, error) {
	if c.request.Tool == "pr-title" {
		return c.prTitle()
	}
	if c.request.Tool == "pr-body" {
		return c.prBody(ctx)
	}
	switch c.request.Tool {
	case "authority-boundary", "assurance-policy", "repo-policy":
	case "adr-immutability", "agent-guidance", "contract-requirement-tracing", "requirement-context", "requirement-governance", "project-positioning", "deprecation-lifecycle", "identity-cutover", "concept-authority-governance":
	case attackVocabularyCheck, atlasVocabularyCheck, nistVocabularyCheck, autonomousVocabularyCheck:
	case schemaPublicationCheck, jsonArtifactCheck, schemaCoverageCheck, "public-docs-reads", "public-docs":
	default:
		return Report{}, errors.New("governance check is not implemented")
	}
	r, err := openRepository(c.request.Root)
	if err != nil {
		return Report{}, err
	}
	defer func() { _ = r.root.Close() }()
	return c.checkRepository(ctx, r)
}

func (c *checker) checkRepository(ctx context.Context, r *repository) (Report, error) {
	switch c.request.Tool {
	case "repo-policy":
		return c.repoPolicy(ctx, r)
	case "assurance-policy":
		return c.assurance(r)
	case "authority-boundary":
		return c.authorityBoundary(r)
	case "public-docs":
		return c.publicDocumentation(r)
	case "public-docs-reads":
		return c.documentationReads(r)
	case schemaCoverageCheck:
		return c.schemaCoverage(r)
	case jsonArtifactCheck:
		return c.jsonArtifacts(ctx, r)
	case schemaPublicationCheck:
		return c.schemaPublication(ctx, r)
	case "concept-authority-governance":
		return c.conceptAuthority(r)
	case "identity-cutover":
		return identityCutover(ctx, r)
	case attackVocabularyCheck, atlasVocabularyCheck, nistVocabularyCheck, autonomousVocabularyCheck:
		return c.vocabulary(ctx, r)
	case "requirement-governance":
		return c.requirementGovernance(ctx, r)
	case "requirement-context":
		return c.requirementContext(ctx, r)
	case "agent-guidance":
		return c.finish(r, agentGuidance(r))
	case "project-positioning":
		return c.projectPositioning(ctx, r)
	case "deprecation-lifecycle":
		findings, err := deprecation(r)
		if err != nil {
			return Report{}, err
		}
		return c.finish(r, findings)
	case "contract-requirement-tracing":
		report, err := contractTracing(r, c.request.Mode)
		if err != nil || c.request.Mode == Inventory {
			return report, err
		}
		return c.finish(r, report.Findings)
	default:
		report, err := c.adr(ctx, r)
		if err != nil {
			return report, err
		}
		return c.finish(r, report.Findings)
	}
}
