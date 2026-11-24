package analysis

import (
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// Request selects an analysis and its explicit inputs.
type Request struct {
	Kind        string
	Compilation processor.Compilation
	Options     map[string]any
	Source      *SourceInput
	Input       *JSONInput
	Comparison  *ComparisonInput
	Authoring   *AuthoringInput
	Solver      *Solver
}

// Result contains admitted evidence and any native companion artifacts.
type Result struct {
	Document        map[string]any
	Diagnostics     []diagnostic.Diagnostic
	CandidateSource *string
	Candidate       sdl.Scenario
	SemanticResult  validation.Value
}

// SourceInput binds an SDL source context to strict parsing limits.
type SourceInput struct {
	Source  sdl.SourceContext
	Options sdl.ParseOptions
}

// JSONInput carries bounded JSON with optional admitted profile and catalog authority.
type JSONInput struct {
	SourceID string
	Data     []byte
	Profile  validation.Value
	Catalog  validation.Value
}

// ComparisonInput binds both native artifacts to a governed comparison request.
type ComparisonInput struct {
	Profile       profile.ComparisonProfile
	Request       validation.Value
	Before, After comparison.Artifact
	Options       comparison.Options
}

// AuthoringOutput carries one untrusted authoring path result and its provenance.
type AuthoringOutput struct {
	InputSource          string
	OutputSource         *string
	Diagnostics          []diagnostic.Diagnostic
	TransformationReport validation.Value
}

// AuthoringInput compares two path outputs against an admitted reference vector.
type AuthoringInput struct {
	Vector              validation.Value
	Left, Right         AuthoringOutput
	LeftPath, RightPath string
}
