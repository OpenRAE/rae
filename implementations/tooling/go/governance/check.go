// Package governance checks repository policy against its existing authorities.
// It does not define policy or grant authority to candidate repository content.
package governance

import (
	"context"
	"errors"
)

// Finding is a stable reference-tool finding. A nil Path is JSON null.
type Finding struct {
	RuleID  string  `json:"rule_id"`
	Message string  `json:"message"`
	Path    *string `json:"path"`
}

// Request selects a check and its explicit inputs. Today is an ISO date,
// supplied by the caller for deterministic exception and lifecycle evaluation.
// Body and Title are untrusted PR text. IssueFacts holds read-only lookup data.
type Request struct {
	Tool              string
	Root              string
	Paths             []string
	BaseRevision      string
	RequirementUID    string
	Today             string
	Body              string
	Title             string
	CommitMessages    string
	Repository        string
	IssueFacts        []byte
	RequireGovernance bool
	Staged            bool
}

// Report distinguishes evaluated policy from unavailable optional governance.
// Findings retain reference order. Status is empty for an evaluated policy.
type Report struct {
	Findings []Finding
	Status   string
}

// Check evaluates the named repository policy. An unsupported check refuses
// evaluation; it must never be mistaken for a successful policy verdict.
func Check(ctx context.Context, request Request) (Report, error) {
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	return Report{}, errors.New("governance check is not implemented")
}
