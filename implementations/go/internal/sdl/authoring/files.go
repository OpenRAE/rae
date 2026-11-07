package authoring

import (
	"errors"
	"io/fs"
	"path"
	"slices"
	"strings"
)

type pathPart struct{ token, leave string }
type filesystemPath struct {
	composition *composition
	prefix      []string
	pending     []pathPart
	active      map[string]bool
	missing     int
}

// fileName resolves only within the caller filesystem. Components are walked
// before cleaning, so link/.. has the same meaning as Path.resolve(strict=False).
func (c *composition) fileName(name string) (string, error) {
	if c.request.FS == nil {
		return "", importError("source-missing")
	}
	parts, _, err := c.fileParts(name)
	if err != nil {
		return "", err
	}
	walk := filesystemPath{composition: c, active: map[string]bool{}}
	walk.push(parts)
	for len(walk.pending) > 0 {
		step := walk.pending[len(walk.pending)-1]
		walk.pending = walk.pending[:len(walk.pending)-1]
		if step.leave != "" {
			delete(walk.active, step.leave)
			continue
		}
		if err = walk.step(step.token); err != nil {
			return "", err
		}
	}
	if len(walk.prefix) == 0 {
		return "", importError("path-invalid")
	}
	return strings.Join(walk.prefix, "/"), nil
}
func (w *filesystemPath) push(parts []string) {
	for _, part := range slices.Backward(parts) {
		w.pending = append(w.pending, pathPart{token: part})
	}
}
func (w *filesystemPath) step(token string) error {
	switch token {
	case "", ".":
		return nil
	case "..":
		if len(w.prefix) == 0 {
			if w.composition.request.RootDir == "/" {
				return nil
			}
			return importError("path-invalid")
		}
		w.prefix = w.prefix[:len(w.prefix)-1]
		if len(w.prefix) < w.missing {
			w.missing = 0
		}
		return nil
	}
	if w.missing > 0 {
		w.prefix = append(w.prefix, token)
		return nil
	}
	candidate := strings.Join(append(slices.Clone(w.prefix), token), "/")
	if !fs.ValidPath(candidate) {
		return importError("path-invalid")
	}
	info, err := fs.Lstat(w.composition.request.FS, candidate)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return importReadError(err)
	}
	if err != nil {
		w.prefix = append(w.prefix, token)
		w.missing = len(w.prefix)
		return nil //nolint:nilerr // A missing component remains lexical under strict=False resolution.
	}
	if info.Mode()&fs.ModeSymlink == 0 {
		w.prefix = append(w.prefix, token)
		return nil
	}
	return w.link(candidate)
}
func (w *filesystemPath) link(name string) error {
	if w.active[name] {
		return importError("source-missing")
	}
	reader, ok := w.composition.request.FS.(fs.ReadLinkFS)
	if !ok {
		return importReadError(fs.ErrInvalid)
	}
	target, err := reader.ReadLink(name)
	if err != nil {
		return importReadError(err)
	}
	parts, absolute, err := w.composition.fileParts(target)
	if err != nil {
		return err
	}
	if absolute {
		w.prefix = nil
		w.missing = 0
	}
	w.active[name] = true
	w.pending = append(w.pending, pathPart{leave: name})
	w.push(parts)
	return nil
}
func (c *composition) fileParts(name string) ([]string, bool, error) {
	if name == "" || strings.ContainsRune(name, 0) {
		return nil, false, importError("path-invalid")
	}
	absolute := path.IsAbs(name)
	if absolute {
		root := c.request.RootDir
		if root == "" {
			return nil, false, importError("path-invalid")
		}
		prefix := strings.TrimSuffix(root, "/") + "/"
		if !strings.HasPrefix(name, prefix) {
			return nil, false, importError("path-invalid")
		}
		name = strings.TrimPrefix(name, prefix)
	}
	return strings.Split(name, "/"), absolute, nil
}
