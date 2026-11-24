package authoring

import (
	"context"
	"io/fs"
	"path"
	"slices"
	"strings"

	sdlsource "github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// AdmitModuleSources captures the exact local graph checked by native source
// construction and composition. It grants no semantic or execution admission.
func (p *Parser) AdmitModuleSources(ctx context.Context, source fs.FS, root string) (string, map[string][]byte, error) {
	if err := ctx.Err(); err != nil {
		return "", nil, err
	}
	c := composition{parser: p, request: Request{FS: source, Name: root}, seen: map[string]bool{}, localDenied: map[string]bool{}, records: map[string][]map[string]any{}, snapshot: map[string][]byte{}}
	var err error
	c.budget, err = sdlsource.NewBudget(p.limits)
	if err != nil {
		return "", nil, err
	}
	c.copies.remaining = p.limits.MaxComposedBytes
	name, err := c.fileName(root)
	if err != nil {
		return "", nil, err
	}
	raw, err := c.read(name)
	if err != nil {
		return "", nil, err
	}
	document, err := p.decode(raw, name, "reject")
	if err != nil {
		return "", nil, err
	}
	value, err := p.modelValue(document)
	if err != nil {
		return "", nil, err
	}
	expanded, err := c.expand(ctx, document, value, name, 0)
	if err != nil {
		return "", nil, err
	}
	if err = c.retainExpanded(document, expanded, name); err != nil {
		return "", nil, err
	}
	result := make(map[string][]byte, len(c.snapshot))
	prefix := path.Dir(name)
	for name, raw := range c.snapshot {
		if !withinDirectory(prefix, name) {
			return "", nil, importError(pathInvalidCode)
		}
		relative := name
		if prefix != "." {
			relative = strings.TrimPrefix(name, prefix+"/")
		}
		result[relative] = slices.Clone(raw)
	}
	if err = ctx.Err(); err != nil {
		return "", nil, err
	}
	return path.Base(name), result, nil
}
