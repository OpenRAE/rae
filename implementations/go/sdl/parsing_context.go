package sdl

import (
	"context"
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
)

// ParseWithContext admits source bytes under caller cancellation.
//
//nolint:ireturn // The declared SDL API returns a sealed native source handle.
func ParseWithContext(ctx context.Context, source []byte, options ParseOptions) (Scenario, error) {
	return parseRequest(ctx, authoring.Request{Source: source}, options, true)
}

// ParseFileWithContext admits contained source files under caller cancellation.
//
//nolint:ireturn // The declared SDL API returns a sealed native source handle.
func ParseFileWithContext(ctx context.Context, source fs.FS, root string, options ParseOptions) (Scenario, error) {
	if err := checkParsingContext(ctx); err != nil {
		return nil, err
	}
	if err := options.Validate(); err != nil {
		return nil, err
	}
	if source == nil || !fs.ValidPath(root) || root == "." {
		return nil, invalidScenario()
	}
	file, err := source.Open(root)
	if err != nil {
		return nil, fault.New(fault.Operational, "sdl-source-read", err)
	}
	raw, err := readSource(file, options.Limits.MaxInputBytes)
	if err != nil {
		return nil, err
	}
	return parseRequest(ctx, authoring.Request{Source: raw, Name: root, FS: source}, options, true)
}

// ParseSourceWithContext retains explicit source and module authority under caller cancellation.
//
//nolint:ireturn // The declared SDL API returns a sealed native source handle.
func ParseSourceWithContext(ctx context.Context, source SourceContext, options ParseOptions) (Scenario, error) {
	return parseSourceContext(ctx, source, options)
}

func checkParsingContext(ctx context.Context) error {
	if ctx == nil {
		return invalidScenario()
	}
	if err := ctx.Err(); err != nil {
		return fault.New(fault.Operational, "sdl-operation-canceled", err)
	}
	return nil
}
