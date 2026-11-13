package sdl

import (
	"bytes"
	"context"
	"encoding/json"
	"io/fs"
	"path"
	"slices"
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

// SourceContext grants only the supplied source and explicit module authority.
type SourceContext struct {
	Root      string
	RootBytes []byte
	FS        fs.FS
	Sources   map[string][]byte
	Lock      *module.Lockfile
	Trust     module.TrustPolicy
}

// ParseContext composes and validates source using only explicit module and filesystem authority.
//
//nolint:ireturn // The declared SDL API returns a sealed native source handle.
func ParseContext(source SourceContext, options ParseOptions) (Scenario, error) {
	return ParseSourceWithContext(context.Background(), source, options)
}

//nolint:ireturn // The declared SDL API returns a sealed native source handle.
func parseSourceContext(ctx context.Context, source SourceContext, options ParseOptions) (Scenario, error) {
	if err := checkParsingContext(ctx); err != nil {
		return nil, err
	}
	if err := options.Validate(); err != nil {
		return nil, err
	}
	captured, err := captureSourceContext(source, options)
	if err != nil {
		return nil, err
	}
	raw, err := fs.ReadFile(captured, source.Root)
	if err != nil {
		return nil, fault.New(fault.Operational, "sdl-source-read", err)
	}
	request := authoring.Request{Source: raw, Name: source.Root, FS: captured, LocalTrust: source.Trust}
	request.Registry, err = sourceTrustRegistry(source.Trust)
	if err != nil {
		return nil, err
	}
	return parseRequest(ctx, request, options, true)
}

// contextSources freezes each supplied read once, including trust and lock reads.
// It never opens a host path without the caller's filesystem capability.
type contextSources struct {
	provider fs.FS
	supplied map[string][]byte
	limits   Limits
	files    map[string][]byte
	used     int64
}

func (s *contextSources) Stat(name string) (fs.FileInfo, error) {
	if data, exists := s.files[name]; exists {
		return contextInfo{name: name, size: int64(len(data))}, nil
	}
	if s.provider != nil {
		return fs.Stat(s.provider, name)
	}
	return s.suppliedInfo(name)
}

func (s *contextSources) Lstat(name string) (fs.FileInfo, error) {
	if data, exists := s.files[name]; exists {
		return contextInfo{name: name, size: int64(len(data))}, nil
	}
	if s.provider != nil {
		return fs.Lstat(s.provider, name)
	}
	return s.suppliedInfo(name)
}

func (s *contextSources) ReadLink(name string) (string, error) {
	if !fs.ValidPath(name) || s.provider == nil {
		return "", &fs.PathError{Op: "readlink", Path: name, Err: fs.ErrInvalid}
	}
	return fs.ReadLink(s.provider, name)
}

func (s *contextSources) suppliedInfo(name string) (fs.FileInfo, error) {
	if !fs.ValidPath(name) {
		return nil, &fs.PathError{Op: "stat", Path: name, Err: fs.ErrInvalid}
	}
	if data, exists := s.supplied[name]; exists {
		return contextInfo{name: name, size: int64(len(data))}, nil
	}
	for candidate := range s.supplied {
		if strings.HasPrefix(candidate, name+"/") {
			return contextInfo{name: name, directory: true}, nil
		}
	}
	return nil, &fs.PathError{Op: "stat", Path: name, Err: fs.ErrNotExist}
}

func (s *contextSources) retain(name string, raw []byte) error {
	if !fs.ValidPath(name) || int64(len(raw)) > s.limits.MaxInputBytes || int64(len(raw)) > s.limits.MaxComposedBytes-s.used {
		return invalidScenario()
	}
	if _, exists := s.files[name]; exists {
		return invalidScenario()
	}
	s.used += int64(len(raw))
	s.files[name] = slices.Clone(raw)
	return nil
}

func (s *contextSources) Open(name string) (fs.File, error) {
	if !fs.ValidPath(name) {
		return nil, &fs.PathError{Op: termOpen, Path: name, Err: fs.ErrInvalid}
	}
	if data, exists := s.files[name]; exists {
		return &contextFile{Reader: *bytes.NewReader(data), name: name}, nil
	}
	var raw []byte
	switch {
	case s.supplied != nil:
		var exists bool
		raw, exists = s.supplied[name]
		if !exists {
			return nil, &fs.PathError{Op: termOpen, Path: name, Err: fs.ErrNotExist}
		}
	case s.provider != nil:
		file, err := s.provider.Open(name)
		if err != nil {
			return nil, err
		}
		info, statErr := file.Stat()
		if statErr != nil || !info.Mode().IsRegular() {
			_ = file.Close()
			return nil, invalidScenario()
		}
		raw, err = readSource(file, s.limits.MaxInputBytes)
		if err != nil {
			return nil, err
		}
	default:
		return nil, &fs.PathError{Op: termOpen, Path: name, Err: fs.ErrNotExist}
	}
	if err := s.retain(name, raw); err != nil {
		return nil, err
	}
	return &contextFile{Reader: *bytes.NewReader(s.files[name]), name: name}, nil
}

type contextFile struct {
	bytes.Reader

	name string
}

func (*contextFile) Close() error { return nil }
func (f *contextFile) Stat() (fs.FileInfo, error) {
	return contextInfo{name: f.name, size: f.Size()}, nil
}

type contextInfo struct {
	name      string
	size      int64
	directory bool
}

func (i contextInfo) Name() string { return path.Base(i.name) }
func (i contextInfo) Size() int64  { return i.size }
func (i contextInfo) Mode() fs.FileMode {
	if i.directory {
		return fs.ModeDir | 0500
	}
	return 0400
}
func (contextInfo) ModTime() time.Time { return time.Time{} }
func (i contextInfo) IsDir() bool      { return i.directory }
func (contextInfo) Sys() any           { return nil }

func lockBytes(lock module.Lockfile) ([]byte, error) {
	rows := make([]map[string]string, len(lock.Imports))
	for index, record := range lock.Imports {
		rows[index] = map[string]string{
			"source": record.Source, "namespace": record.Namespace, "requested_version": record.RequestedVersion,
			"resolved_source": record.ResolvedSource, "module_id": record.ModuleID, "module_version": record.ModuleVersion,
			"manifest_digest": record.ManifestDigest, "content_digest": record.ContentDigest,
			"export_hash": record.ExportHash, "signer_id": record.SignerID,
		}
	}
	raw, err := json.Marshal(struct {
		Version string              `json:"schema_version"`
		Imports []map[string]string `json:"imports"`
	}{lock.SchemaVersion, rows})
	if err != nil {
		return nil, invalidScenario()
	}
	if _, err := module.DecodeLockfile(raw); err != nil {
		return nil, err
	}
	return raw, nil
}

func captureSourceContext(source SourceContext, options ParseOptions) (*contextSources, error) {
	if !fs.ValidPath(source.Root) || source.Root == "." || source.FS != nil && source.Sources != nil {
		return nil, invalidScenario()
	}
	captured := &contextSources{provider: source.FS, supplied: source.Sources, limits: options.Limits, files: map[string][]byte{}}
	if source.RootBytes != nil {
		if err := captured.retain(source.Root, source.RootBytes); err != nil {
			return nil, err
		}
	}
	if source.Lock != nil {
		raw, err := lockBytes(*source.Lock)
		if err != nil {
			return nil, err
		}
		if err := captured.retain(path.Join(path.Dir(source.Root), module.LockfileName), raw); err != nil {
			return nil, err
		}
	}
	return captured, nil
}

func sourceTrustRegistry(trust module.TrustPolicy) (*module.Registry, error) {
	if registry, ok := trust.(*module.Registry); ok {
		if registry == nil {
			return nil, invalidScenario()
		}
		return registry, nil
	}
	return nil, nil //nolint:nilnil // A narrowing trust callback grants no registry access.
}
