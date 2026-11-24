package module

import (
	"context"
	"errors"
	"io/fs"
	"testing"
)

type publicationSourceFixture struct {
	root    string
	files   map[string][]byte
	failure error
}

func (f publicationSourceFixture) AdmitModuleSources(ctx context.Context, _ fs.FS, _ string) (string, map[string][]byte, error) {
	if err := ctx.Err(); err != nil {
		return "", nil, err
	}
	return f.root, f.files, f.failure
}

func TestPublicationRefusesInvalidInputsAtomically(t *testing.T) {
	fixture := readModuleReference(t)
	for _, name := range []string{"nil-admitter", "failed-admission", "root-escape", "missing-root", "missing-descriptor", "signer-only", "key-only", "invalid-key", "public-key-block", "empty-output", "member-budget", "total-budget", "tar-budget", "compressed-budget"} {
		t.Run(name, func(t *testing.T) { checkPublicationRefusal(t, fixture, name) })
	}
}

func checkPublicationRefusal(t *testing.T, fixture moduleReference, name string) {
	t.Helper()
	registry := referenceRegistry(t, fixture)
	input := publicationSourceFixture{root: fixture.Root, files: map[string][]byte{fixture.Root: fixture.Source}}
	var admitter PublicationAdmitter = input
	output := t.TempDir()
	signer := ""
	var key []byte
	switch name {
	case "nil-admitter":
		admitter = nil
	case "failed-admission":
		input.failure = errors.New("source admission refused")
		admitter = input
	case "root-escape":
		input.root = "../module.yaml"
		admitter = input
	case "missing-root":
		input.files = map[string][]byte{}
		admitter = input
	case "missing-descriptor":
		input.files = map[string][]byte{fixture.Root: []byte("name: missing\n")}
		admitter = input
	case "signer-only":
		signer = "test"
	case "key-only":
		key = []byte("invalid")
	case "invalid-key":
		signer = "test"
		key = []byte("invalid")
	case "public-key-block":
		signer = "test"
		key = []byte("-----BEGIN PUBLIC KEY-----\nAA==\n-----END PUBLIC KEY-----\n")
	case "empty-output":
		output = ""
	case "member-budget":
		registry.limits.memberBytes = 1
	case "total-budget":
		registry.limits.totalBytes = 1
	case "tar-budget":
		registry.limits.tarBytes = 1
	case "compressed-budget":
		registry.limits.bundleBytes = 1
	}
	publication, err := registry.Publish(t.Context(), nil, fixture.Root, output, signer, key, admitter)
	if err == nil || publication != (Publication{}) {
		t.Fatalf("%s returned a publication: %+v %v", name, publication, err)
	}
}

func TestTagSelectionUsesVersionsAndOpaqueFallback(t *testing.T) {
	for _, row := range []struct {
		request  string
		tags     []string
		expected string
	}{
		{"*", []string{"opaque-a", "opaque-z"}, "opaque-z"},
		{"*", nil, ""},
		{">=3", []string{"1.0", "invalid"}, ""},
		{"*", []string{"1.0", "1.0.0", "1.0+abc", "1.0+2"}, "1.0+2"},
		{"==1!1.*", []string{"0!5.0", "1!1.1", "1!2.0"}, "1!1.1"},
	} {
		spec, err := versionSpec(row.request)
		if err != nil {
			t.Fatal(err)
		}
		got, err := selectTag(row.tags, spec)
		if got != row.expected || (err != nil) != (row.expected == "") {
			t.Fatalf("tag selection %q: %q %v", row.request, got, err)
		}
	}
}
