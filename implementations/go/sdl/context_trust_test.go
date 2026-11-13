package sdl_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/sdl"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

type localImportTrust struct {
	reject string
	facts  []module.VerificationFacts
}

func (policy *localImportTrust) AdmitModule(_ context.Context, facts module.VerificationFacts) error {
	policy.facts = append(policy.facts, facts)
	if facts.Record.ModuleID == policy.reject {
		return errors.New("module rejected by supplied trust")
	}
	return nil
}

func localTrustSources() fstest.MapFS {
	return fstest.MapFS{
		"root.yaml":  {Data: []byte("name: root\nimports: [{path: child.yaml, namespace: outer}]\n")},
		"child.yaml": {Data: []byte("name: child\nmodule: {id: example/child, version: 1.0.0, exports: {}}\nimports: [{path: leaf.yaml, namespace: inner}]\n")},
		"leaf.yaml":  {Data: []byte("name: leaf\nmodule: {id: example/leaf, version: 1.0.0, exports: {}}\n")},
	}
}

func TestSourceContextSuppliedTrustGovernsTransitiveLocalImports(t *testing.T) {
	policy := &localImportTrust{reject: "example/leaf"}
	if _, err := sdl.ParseContext(sdl.SourceContext{Root: "root.yaml", FS: localTrustSources(), Trust: policy}, sdl.DefaultParseOptions()); err == nil {
		t.Fatal("transitive local module bypassed caller trust")
	}
	found := false
	for _, facts := range policy.facts {
		found = found || facts.Record.ModuleID == policy.reject
	}
	if !found {
		t.Fatal("supplied trust never saw the transitive module")
	}
}

func TestSourceContextRegistryPolicyGovernsLocalImports(t *testing.T) {
	policy := module.DefaultPolicy()
	policy.AllowUnsignedLocalSources = false
	registry, err := module.NewRegistry(t.TempDir(), policy, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	if _, err := sdl.ParseContext(sdl.SourceContext{Root: "root.yaml", FS: localTrustSources(), Trust: registry}, sdl.DefaultParseOptions()); err == nil {
		t.Fatal("local import bypassed registry policy")
	}
}

func TestSourceContextRegistryNarrowingTrustGovernsTransitiveImports(t *testing.T) {
	trust := &localImportTrust{reject: "example/leaf"}
	registry, err := module.NewRegistry(t.TempDir(), module.DefaultPolicy(), trust)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	if _, err := sdl.ParseContext(sdl.SourceContext{Root: "root.yaml", FS: localTrustSources(), Trust: registry}, sdl.DefaultParseOptions()); err == nil {
		t.Fatal("nested local import bypassed registry narrowing callback")
	}
}

func TestSourceContextTrustReceivesOnlyVerifiedLocalFacts(t *testing.T) {
	trust := &localImportTrust{}
	if _, err := sdl.ParseContext(sdl.SourceContext{Root: "root.yaml", FS: localTrustSources(), Trust: trust}, sdl.DefaultParseOptions()); err != nil {
		t.Fatal(err)
	}
	if len(trust.facts) != 2 {
		t.Fatalf("got %d admitted modules, want both local imports", len(trust.facts))
	}
	for _, facts := range trust.facts {
		if !facts.LocalSource || !facts.ContentVerified || !facts.ExportsVerified || facts.ManifestVerified || facts.SignatureVerified || !strings.HasPrefix(facts.Record.ContentDigest, "sha256:") || len(facts.Record.ExportHash) != 64 {
			t.Fatalf("callback received incomplete integrity facts: %+v", facts)
		}
	}
	files := localTrustSources()
	files["root.yaml"].Data = []byte("name: root\nimports: [{path: child.yaml, namespace: outer, digest: 'sha256:" + strings.Repeat("0", 64) + "'}]\n")
	trust.facts = nil
	if _, err := sdl.ParseContext(sdl.SourceContext{Root: "root.yaml", FS: files, Trust: trust}, sdl.DefaultParseOptions()); err == nil || len(trust.facts) != 0 {
		t.Fatal("trust callback ran before native integrity verification")
	}
}
