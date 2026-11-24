package parity

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestPublicationComparisonKeepsStableIdentity(t *testing.T) {
	caseValue := Case{Surface: "cli", Command: "sdl publish", Args: []string{"sdl", "publish", "root.yaml", "--output-dir", "dist"}}
	observation := func(nonce string) json.RawMessage {
		hash := strings.Repeat("a", 64)
		layout := "dist/example_module-1.0.0.oci/versions/" + hash[:20] + "-" + nonce
		result := map[string]any{"exit_code": 0, "stdout": map[string]any{"module_id": "example/module", "module_version": "1.0.0", "manifest_digest": "sha256:" + hash, "content_digest": "sha256:" + strings.Repeat("b", 64), "layout_dir": layout}, "generated_files": map[string]any{layout + "/index.json": map[string]any{"manifest": "sha256:" + hash}}}
		raw, err := json.Marshal(result)
		if err != nil {
			t.Fatal(err)
		}
		return raw
	}
	want, got := observation(strings.Repeat("1", 20)), observation(strings.Repeat("2", 20))
	diff, err := compareCaseResults(caseValue, want, got)
	if err != nil || diff != "" {
		t.Fatalf("independent valid nonces differ: %s %v", diff, err)
	}
	for name, mutate := range map[string]func(string) string{
		"content digest": func(s string) string { return strings.ReplaceAll(s, strings.Repeat("b", 64), strings.Repeat("c", 64)) },
		"index content":  func(s string) string { return strings.Replace(s, `"manifest":"sha256:`, `"manifest":"changed:`, 1) },
		"wrong prefix": func(s string) string {
			return strings.ReplaceAll(s, "/versions/"+strings.Repeat("a", 20), "/versions/"+strings.Repeat("b", 20))
		},
		"wrong slot":         func(s string) string { return strings.ReplaceAll(s, "example_module-1.0.0.oci", "other-1.0.0.oci") },
		"invalid nonce":      func(s string) string { return strings.ReplaceAll(s, strings.Repeat("2", 20), "invalid") },
		"inconsistent index": func(s string) string { return strings.Replace(s, "/index.json", "/other.json", 1) },
	} {
		t.Run(name, func(t *testing.T) {
			diff, err := compareCaseResults(caseValue, want, []byte(mutate(string(got))))
			if err == nil && diff == "" {
				t.Fatal("stable publication change was ignored")
			}
		})
	}
}
