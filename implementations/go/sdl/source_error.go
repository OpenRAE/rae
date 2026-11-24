package sdl

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type sourceError struct {
	cause    error
	findings []diagnostic.Diagnostic
}

func (e *sourceError) Error() string            { return "invalid-input: " + e.Code() }
func (e *sourceError) Code() string             { return e.findings[0].Code }
func (e *sourceError) Category() fault.Category { return fault.InvalidInput }
func (e *sourceError) Unwrap() error            { return e.cause }
func (e *sourceError) Diagnostics() []diagnostic.Diagnostic {
	result := slices.Clone(e.findings)
	for i := range result {
		if result[i].Range != nil {
			value := *result[i].Range
			result[i].Range = &value
		}
	}
	return result
}

func publicSourceError(err error) error {
	rows := source.Diagnostics(err)
	if len(rows) == 0 {
		return err
	}
	findings := make([]diagnostic.Diagnostic, 0, len(rows))
	for _, row := range rows {
		findings = append(findings, diagnostic.Diagnostic{
			Code: row.Code, Severity: row.Severity, Stage: "parse", Source: row.Source, Pointer: row.Pointer,
			Range: &diagnostic.Range{StartLine: row.Range.Start.Line, StartColumn: row.Range.Start.Column, EndLine: row.Range.End.Line, EndColumn: row.Range.End.Column},
		})
	}
	return &sourceError{cause: err, findings: findings}
}
