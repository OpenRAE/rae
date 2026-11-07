package source

import (
	"path"
	"slices"
	"strings"
)

// Sources owns an immutable snapshot of caller-supplied source bytes.
// It has no filesystem, process, environment, trust or network access.
type Sources struct{ documents map[string][]byte }

// Capture copies supplied buffers after validating each logical path.
// Unused source documents are not parsed and grant no authority.
func Capture(documents map[string][]byte) (*Sources, error) {
	captured := make(map[string][]byte, len(documents))
	for name, data := range documents {
		if !canonicalPath(name) {
			return nil, importFailure(pathInvalidCode)
		}
		captured[name] = slices.Clone(data)
	}
	return &Sources{documents: captured}, nil
}
func canonicalPath(name string) bool {
	parts := strings.Split(name, "/")
	if name == "" || strings.ContainsAny(name, "\\\x00") || strings.Contains(parts[0], ":") {
		return false
	}
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	return true
}

// Bytes returns a copied document at a canonical path, without reading a host resource.
func (s *Sources) Bytes(name string) ([]byte, error) {
	if !canonicalPath(name) {
		return nil, importFailure(pathInvalidCode)
	}
	data, ok := s.documents[name]
	if !ok {
		return nil, importFailure("source-missing")
	}
	return slices.Clone(data), nil
}

// Decode reads one supplied document with a virtual source identity.
// This is a source decode, not an import-admission or scenario-parse operation.
func (s *Sources) Decode(name string, options Options) (*Document, error) {
	data, err := s.Bytes(name)
	if err != nil {
		return nil, err
	}
	options.Name = "/" + name
	return Decode(data, options)
}

// Resolve joins a relative import path to a canonical logical directory.
// Backslashes are accepted as separators, but traversal cannot leave the bundle.
// The result identifies bytes only; the module owner must still check pins and locks.
func (s *Sources) Resolve(directory, relative string) (string, error) {
	name, err := ResolvePath(directory, relative)
	if err != nil {
		return "", err
	}
	if _, ok := s.documents[name]; !ok {
		return "", importFailure("source-missing")
	}
	return name, nil
}

// ResolvePath applies the shared lexical containment rule for supplied sources.
func ResolvePath(directory, relative string) (string, error) {
	relative = strings.ReplaceAll(relative, "\\", "/")
	if relative == "" || strings.ContainsRune(relative, 0) || strings.HasPrefix(relative, "/") {
		return "", importFailure(pathInvalidCode)
	}
	first, _, _ := strings.Cut(relative, "/")
	if len(first) == 2 && first[1] == ':' {
		return "", importFailure(pathInvalidCode)
	}
	if directory != "." && !canonicalPath(directory) {
		return "", importFailure(pathInvalidCode)
	}
	joined := path.Clean(path.Join(directory, relative))
	if joined == "." || joined == ".." || strings.HasPrefix(joined, "../") {
		return "", importFailure(pathInvalidCode)
	}
	return joined, nil
}
func importFailure(code string) error {
	return failure("sdl.import."+code, startRange(), DefaultOptions())
}
