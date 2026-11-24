package authoring

import (
	"context"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

// Local edges within an admitted bundle consume only its immutable source map.
// Workspace files retain their separate post-verification trust boundary.
func (c *composition) admitLocalTrust(ctx context.Context, importer string, decl, descriptor map[string]any, raw []byte, remote bool) error {
	if remote {
		return nil
	}
	if scope, _ := c.verifiedScope(importer); scope != nil {
		return nil
	}
	trust := c.request.LocalTrust
	if trust == nil && c.request.Registry == nil {
		return nil
	}
	facts, err := localTrustFacts(decl, descriptor, raw)
	if err != nil {
		return err
	}
	if c.request.Registry != nil {
		if err := c.request.Registry.AdmitModule(ctx, facts); err != nil {
			return err
		}
	}
	if registry, ok := trust.(*module.Registry); ok && registry == c.request.Registry {
		return nil
	}
	if trust != nil {
		if err := trust.AdmitModule(ctx, facts); err != nil {
			return fault.New(fault.Authorization, "sdl-module-trust-refused", err)
		}
	}
	return nil
}

func localTrustFacts(decl, descriptor map[string]any, raw []byte) (module.VerificationFacts, error) {
	exports, err := exportDigest(descriptor)
	if err != nil {
		return module.VerificationFacts{}, err
	}
	requested := importSource(decl)
	version := text(decl["version"])
	if version == "" {
		version = "*"
	}
	record := module.LockRecord{
		Source: requested, Namespace: text(decl[namespaceField]), RequestedVersion: version,
		ResolvedSource: strings.TrimPrefix(requested, localImportPrefix),
		ModuleID:       text(descriptor["id"]), ModuleVersion: text(descriptor["version"]),
		ContentDigest: digest.SHA256(raw), ExportHash: strings.TrimPrefix(exports, sha256Prefix),
	}
	return module.VerificationFacts{Record: record, LocalSource: true, ContentVerified: true, ExportsVerified: true}, nil
}
