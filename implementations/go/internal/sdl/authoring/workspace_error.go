package authoring

import (
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type workspaceError struct {
	diagnostic source.Diagnostic
	cause      error
}

func workspaceFailure(name string, cause error) error {
	span := source.Range{Start: source.Position{Line: 1, Column: 1}, End: source.Position{Line: 1, Column: 1}}
	if nested := source.Diagnostics(cause); len(nested) > 0 {
		span = nested[0].Range
	}
	return &workspaceError{cause: cause, diagnostic: source.Diagnostic{Code: "sdl.workspace-config.invalid", Pointer: "", Range: span, Source: name, Severity: termError}}
}

func (e *workspaceError) Error() string            { return "workspace configuration rejected" }
func (e *workspaceError) Category() fault.Category { return fault.InvalidInput }
func (e *workspaceError) Unwrap() error            { return e.cause }
func (e *workspaceError) SourceDiagnostics() []source.Diagnostic {
	return []source.Diagnostic{e.diagnostic}
}
