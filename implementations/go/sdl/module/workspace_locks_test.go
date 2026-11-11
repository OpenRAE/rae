package module

import (
	"encoding/json"
	"io/fs"
	"maps"
	"testing"
	"testing/fstest"
)

func TestWorkspaceLockfileFieldsAndLoading(t *testing.T) {
	row := map[string]any{"source": "local:child.yaml", "namespace": "child", "requested_version": "*", "resolved_source": "child.yaml", "module_id": "example/child", "module_version": "1.0.0", "manifest_digest": "", "content_digest": "sha256:content", "export_hash": "exports", "signer_id": "signer"}
	for key := range row {
		t.Run(key, func(t *testing.T) { checkLockfileField(t, row, key) })
	}
	raw := lockfileTestBytes(t, row)
	files := fstest.MapFS{LockfileName: {Data: raw}}
	lock, err := LoadLockfile(files, ".")
	if err != nil || len(lock.Imports) != 1 || lock.Imports[0].SignerID != "signer" || lock.Imports[0].ContentDigest != "sha256:content" {
		t.Fatalf("lock facts lost: %+v %v", lock, err)
	}
	missing, err := LoadLockfile(files, "missing")
	if err != nil || len(missing.Imports) != 0 {
		t.Fatal("missing lock is not empty", err)
	}
	if _, err = LoadLockfile(nil, "."); err == nil {
		t.Fatal("nil filesystem accepted")
	}
	files[LockfileName] = &fstest.MapFile{Mode: fs.ModeDir}
	if _, err = LoadLockfile(files, "."); err == nil {
		t.Fatal("directory accepted as lock")
	}
}

func lockfileTestBytes(t *testing.T, row map[string]any) []byte {
	t.Helper()
	raw, err := json.Marshal(map[string]any{"schema_version": "raes-lock/v1", "imports": []any{row}})
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func checkLockfileField(t *testing.T, row map[string]any, key string) {
	t.Helper()
	missing := maps.Clone(row)
	delete(missing, key)
	lock, err := DecodeLockfile(lockfileTestBytes(t, missing))
	optional := key == "requested_version" || key == "signer_id"
	if (err == nil) != optional {
		t.Fatalf("missing %s admission: %v", key, err)
	}
	if optional && len(lock.Imports) != 1 {
		t.Fatal("optional field lost record")
	}
	wrong := maps.Clone(row)
	wrong[key] = 42
	if _, err = DecodeLockfile(lockfileTestBytes(t, wrong)); err == nil {
		t.Fatalf("non-string %s accepted", key)
	}
	unknown := maps.Clone(row)
	unknown["unknown"] = true
	if _, err = DecodeLockfile(lockfileTestBytes(t, unknown)); err == nil {
		t.Fatal("unknown field accepted")
	}
}

func TestWorkspaceResolutionLoadsExplicitPolicy(t *testing.T) {
	files := fstest.MapFS{"main.yaml": {Data: []byte("name: root\nimports: [{path: child.yaml, namespace: child}]\n")}, "child.yaml": {Data: []byte("name: child\nmodule: {id: example/child, version: 1.0.0, exports: {}}\n")}}
	for _, policy := range []string{"allow_unsigned_local_sources: true", "allow_unsigned_local_sources: false", "registries: []"} {
		t.Run(policy, func(t *testing.T) {
			files["raes-trust.yaml"] = &fstest.MapFile{Data: []byte(policy)}
			lock, err := ResolveLock(t.Context(), files, "main.yaml", nil)
			if policy == "allow_unsigned_local_sources: true" {
				if err != nil || len(lock.Imports) != 1 {
					t.Fatal("explicit local authority refused", err)
				}
			} else if err == nil {
				t.Fatal("workspace policy refusal ignored")
			}
		})
	}
	registry, err := NewRegistry(t.TempDir(), DefaultPolicy(), nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	if lock, err := ResolveLock(t.Context(), files, "main.yaml", registry); err != nil || len(lock.Imports) != 1 {
		t.Fatal("explicit registry must own its policy", err)
	}
	if _, err := registry.ResolveLock(t.Context(), files, "main.yaml", nil); err == nil {
		t.Fatal("nil source admitter accepted")
	}
}
