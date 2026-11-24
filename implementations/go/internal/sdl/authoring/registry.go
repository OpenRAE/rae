package authoring

import (
	"context"
	"path"
	"path/filepath"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

type verifiedSources struct {
	root    string
	sources verifiedSourceMap
}

// This private map can be created only from a verified Bundle's copied sources.
// Its filenames follow the archive profile; caller source maps retain their
// separate source.Capture path policy.
type verifiedSourceMap map[string][]byte

func (s verifiedSourceMap) Bytes(name string) ([]byte, error) {
	raw, present := s[name]
	if !present {
		return nil, importError("source-missing")
	}
	return slices.Clone(raw), nil
}
func (s verifiedSourceMap) Resolve(directory, relative string) (string, error) {
	joined, err := source.ResolvePath(path.Join("verified", directory), relative)
	if err != nil {
		return "", err
	}
	name, inside := strings.CutPrefix(joined, "verified/")
	if !inside {
		return "", importError("path-invalid")
	}
	if _, present := s[name]; !present {
		return "", importError("source-missing")
	}
	return name, nil
}

func (c *composition) verifiedScope(name string) (*verifiedSources, string) {
	for prefix, scope := range c.verified {
		if after, ok := strings.CutPrefix(name, prefix+"/"); ok {
			return scope, after
		}
	}
	return nil, ""
}
func (c *composition) importBytes(ctx context.Context, decl map[string]any, requested, importer string, lock *lockfile) (string, []byte, bool, error) {
	if after, ok := strings.CutPrefix(requested, localImportPrefix); ok {
		name, err := c.localName(importer, after)
		if err != nil {
			return "", nil, false, err
		}
		raw, err := c.read(name)
		return name, raw, false, err
	}
	if c.supplied != nil || c.request.Registry == nil {
		return "", nil, false, importError("source-refused")
	}
	version := text(decl["version"])
	locked, present, err := matchingLockRecord(lock, decl, requested, false)
	if err != nil {
		return "", nil, false, err
	}
	var bundle *module.Bundle
	if present {
		record := module.LockRecord{Source: requested, RequestedVersion: version, ManifestDigest: text(locked[manifestDigestField]), ContentDigest: text(locked[contentDigestField]), ModuleID: text(locked[moduleIDField]), ExportHash: text(locked[exportHashField])}
		bundle, err = c.request.Registry.ResolveLocked(ctx, record)
		if err == nil && !pinMatchesDigest(bundle.Record().ContentDigest, text(decl["digest"])) {
			err = importError("digest-mismatch")
		}
	} else {
		bundle, err = c.request.Registry.Resolve(ctx, requested, version, text(decl["digest"]))
	}
	if err != nil {
		return "", nil, false, err
	}
	root := filepath.ToSlash(bundle.RootPath())
	prefix := strings.TrimSuffix(root, "/"+bundle.RootFile())
	sources := verifiedSourceMap(bundle.Sources())
	if c.verified == nil {
		c.verified = map[string]*verifiedSources{}
		c.remoteFacts = map[string]module.LockRecord{}
	}
	c.verified[prefix] = &verifiedSources{root: prefix, sources: sources}
	c.remoteFacts[root] = bundle.Record()
	raw, err := sources.Bytes(bundle.RootFile())
	return root, raw, true, err
}
func pinMatchesDigest(actual, pin string) bool {
	return pin == "" || strings.TrimPrefix(actual, sha256Prefix) == strings.TrimPrefix(pin, sha256Prefix)
}
