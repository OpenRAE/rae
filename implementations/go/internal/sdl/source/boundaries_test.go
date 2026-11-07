package source

import (
	"errors"
	"io"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestSourceReadBoundaries(t *testing.T) {
	options := DefaultOptions()
	options.Limits.MaxInputBytes = 5
	files := fstest.MapFS{"input.yaml": {Data: []byte("x: y\n")}, "oversize.yaml": {Data: []byte("x: yy\n")}, "utf8.yaml": {Data: []byte{0xff}}}
	doc, err := Read(files, "input.yaml", options)
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(map[string]any{"x": "y"}, doc.Value()); diff != "" {
		t.Fatalf("Read() mismatch (-want +got):\n%s", diff)
	}
	for _, tc := range []struct{ name, code string }{{"oversize.yaml", "sdl.source_limit"}, {"utf8.yaml", "sdl.utf8"}} {
		_, err := Read(files, tc.name, options)
		ds := Diagnostics(err)
		if len(ds) != 1 || ds[0].Code != tc.code || ds[0].Source != tc.name {
			t.Errorf("Read(%q) diagnostics = %+v, want %s with source", tc.name, ds, tc.code)
		}
	}
	if _, err := Read(files, "../input.yaml", options); err == nil {
		t.Fatal("Read() accepted a parent path")
	}
	if _, err := Read(files, "missing.yaml", options); !errors.Is(err, fs.ErrNotExist) {
		t.Errorf("Read() error = %v, want not-exist", err)
	}
	options.Limits.MaxInputBytes = 0
	if _, err := Read(files, "input.yaml", options); err == nil {
		t.Fatal("Read() accepted an invalid limit")
	}
}

func TestSourceOptionsAndImmutability(t *testing.T) {
	options := DefaultOptions()
	options.MigrationPolicy = "accept"
	options.Name = "source.yaml"
	doc, err := Decode([]byte("Field-Name: {Nested: [x]}\n"), options)
	if err != nil {
		t.Fatal(err)
	}
	value, ok := doc.Value().(map[string]any)
	if !ok {
		t.Fatal("Value() has no mapping")
	}
	value["Field-Name"] = "changed"
	warnings := doc.Diagnostics()
	warnings[0].AuthoredKeys[0] = "changed"
	warnings[0].Range.Start.Line = 99
	ranges := doc.Ranges()
	ranges["/field_name"] = Range{}
	if doc.Diagnostics()[0].AuthoredKeys[0] != "Field-Name" {
		t.Fatal("Diagnostics() exposed internal keys")
	}
	expected := map[string]any{"field_name": map[string]any{"nested": []any{"x"}}}
	if diff := cmp.Diff(expected, doc.NormalizedValue()); diff != "" {
		t.Errorf("NormalizedValue() mismatch (-want +got):\n%s", diff)
	}
	if doc.Ranges()["/field_name"].Start.Line != 1 {
		t.Fatal("Ranges() exposed internal state")
	}
	if len(doc.KeyRanges()) == 0 {
		t.Fatal("KeyRanges() is empty")
	}
	options.RequireMapping = true
	if _, err := Decode([]byte("[x]\n"), options); err == nil {
		t.Fatal("Decode() accepted a nonmapping document")
	}
	options.RequiredRevision = "rev/v1"
	if _, err := Decode([]byte("semantic_revision: other\n"), options); len(Diagnostics(err)) != 1 || Diagnostics(err)[0].Code != "sdl.import.revision-mismatch" {
		t.Errorf("Decode() revision error = %v", err)
	}
	if _, err := Decode([]byte("semantic_revision: rev/v1\n"), options); err != nil {
		t.Fatal(err)
	}
	options.BasePointer = "bad"
	if _, err := Decode([]byte("a: b\n"), options); err == nil {
		t.Fatal("Decode() accepted an invalid base pointer")
	}
	options = DefaultOptions()
	options.KeyScope = "bad"
	if _, err := Decode([]byte("a: b\n"), options); err == nil {
		t.Fatal("Decode() accepted an invalid key scope")
	}
	if _, err := Decode([]byte{0xff}, DefaultOptions()); len(Diagnostics(err)) != 1 || Diagnostics(err)[0].Code != "sdl.utf8" {
		t.Fatal("Decode() did not refuse invalid UTF-8")
	}
}

func TestAllParserLimitDefinitions(t *testing.T) {
	for i := range 11 {
		limits := DefaultLimits()
		fields := []*int{&limits.MaxDepth, &limits.MaxNodes, &limits.MaxAliases, &limits.MaxExpandedNodes, &limits.MaxImports, &limits.MaxComposedNodes, &limits.MaxCompositionDepth, &limits.MaxNamespaceDepth}
		if i < len(fields) {
			*fields[i] = 0
		} else {
			switch i {
			case 8:
				limits.MaxInputBytes = 0
			case 9:
				limits.MaxScalarBytes = 0
			case 10:
				limits.MaxComposedBytes = 0
			}
		}
		if limits.Validate() == nil {
			t.Errorf("Validate() accepted zero limit %d", i)
		}
		options := DefaultOptions()
		options.Limits = limits
		if _, err := Decode([]byte("x: y\n"), options); err == nil {
			t.Errorf("Decode() accepted invalid limits %d", i)
		}
		if _, err := NewBudget(limits); err == nil {
			t.Errorf("NewBudget() accepted invalid limits %d", i)
		}
	}
}

func TestSuppliedSourceContainment(t *testing.T) {
	supplied := map[string][]byte{"root.yaml": []byte("a: b\n"), "nested/child.yaml": []byte("x: y\n")}
	sources, err := Capture(supplied)
	if err != nil {
		t.Fatal(err)
	}
	supplied["root.yaml"][0] = 'z'
	delete(supplied, "nested/child.yaml")
	data, err := sources.Bytes("root.yaml")
	if err != nil {
		t.Fatal(err)
	}
	data[0] = 'q'
	doc, err := sources.Decode("root.yaml", DefaultOptions())
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(map[string]any{"a": "b"}, doc.Value()); diff != "" {
		t.Errorf("Decode() mismatch (-want +got):\n%s", diff)
	}
	name, err := sources.Resolve("nested", "../root.yaml")
	if err != nil || name != "root.yaml" {
		t.Errorf("Resolve() = %q, %v, want root.yaml", name, err)
	}
	name, err = sources.Resolve(".", `nested\child.yaml`)
	if err != nil || name != "nested/child.yaml" {
		t.Errorf("Resolve() = %q, %v, want nested/child.yaml", name, err)
	}
}

func TestSuppliedSourceRefusals(t *testing.T) {
	sources, err := Capture(map[string][]byte{"root.yaml": []byte("a: b\n")})
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"", "/root.yaml", "../root.yaml", "x/../root.yaml", "./root.yaml", "x//root.yaml", `x\root.yaml`, "C:root.yaml", "x\x00.yaml"} {
		if _, err := Capture(map[string][]byte{name: nil}); err == nil {
			t.Errorf("Capture(%q) succeeded", name)
		}
		if _, err := sources.Bytes(name); err == nil {
			t.Errorf("Bytes(%q) succeeded", name)
		}
	}
	for _, relative := range []string{"", "/root.yaml", "../../root.yaml", `C:\root.yaml`, "..", "x\x00.yaml"} {
		if _, err := sources.Resolve(".", relative); err == nil {
			t.Errorf("Resolve(%q) succeeded", relative)
		}
	}
	if _, err := sources.Resolve("../bad", "root.yaml"); err == nil {
		t.Fatal("Resolve() accepted invalid base")
	}
	if _, err := sources.Resolve(".", "missing.yaml"); err == nil || Diagnostics(err)[0].Code != "sdl.import.source-missing" {
		t.Fatalf("Resolve() missing error = %v", err)
	}
	if _, err := sources.Decode("missing.yaml", DefaultOptions()); err == nil {
		t.Fatal("Decode() accepted a missing source")
	}
}

func TestCompositionBudgetBoundaries(t *testing.T) {
	document, err := Decode([]byte("x: y\n"), DefaultOptions())
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name      string
		configure func(*Limits)
		run       func(*Budget) error
	}{
		{"imports", func(l *Limits) { l.MaxImports = 1 }, func(b *Budget) error {
			if err := b.AddImport(); err != nil {
				return err
			}
			return b.AddImport()
		}},
		{"nodes", func(l *Limits) { l.MaxComposedNodes = 3 }, func(b *Budget) error {
			if err := b.AddDocument(document); err != nil {
				return err
			}
			return b.AddDocument(document)
		}},
		{"decoded bytes", func(l *Limits) { l.MaxComposedBytes = 2 }, func(b *Budget) error {
			if err := b.AddDocument(document); err != nil {
				return err
			}
			return b.AddBytes(1)
		}},
		{"raw bytes", func(l *Limits) { l.MaxComposedBytes = 2 }, func(b *Budget) error {
			if err := b.AddBytes(2); err != nil {
				return err
			}
			return b.AddBytes(1)
		}},
		{"depth", func(l *Limits) { l.MaxCompositionDepth = 2 }, func(b *Budget) error {
			if err := b.CheckDepth(2); err != nil {
				return err
			}
			return b.CheckDepth(3)
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			checkBudgetCase(t, tc.configure, tc.run)
		})
	}
}

func TestNamespaceBoundaries(t *testing.T) {
	limits := DefaultLimits()
	limits.MaxNamespaceDepth = 1
	for _, tc := range []struct{ name, code string }{{"a.b", ""}, {"a.b.c", "sdl.import.budget-exceeded"}, {"A.b", "sdl.import.namespace-invalid"}, {strings.Repeat("a", 2049), "sdl.import.namespace-invalid"}} {
		budget, err := NewBudget(limits)
		if err != nil {
			t.Fatal(err)
		}
		err = budget.CheckNamespace(tc.name)
		if tc.code == "" && err != nil {
			t.Errorf("CheckNamespaces() = %v", err)
		}
		if tc.code != "" && (err == nil || Diagnostics(err)[0].Code != tc.code) {
			t.Errorf("CheckNamespaces() = %v, want %s", err, tc.code)
		}
	}
}

type brokenFS struct{ read bool }

func (b brokenFS) Open(string) (fs.File, error) {
	if !b.read {
		return nil, fs.ErrPermission
	}
	return brokenFile{}, nil
}

type brokenFile struct{}

func (brokenFile) Stat() (fs.FileInfo, error) { return nil, fs.ErrPermission }
func (brokenFile) Read([]byte) (int, error)   { return 0, io.ErrUnexpectedEOF }
func (brokenFile) Close() error               { return nil }
func TestReaderFailures(t *testing.T) {
	for _, fileSystem := range []fs.FS{brokenFS{}, brokenFS{read: true}} {
		if _, err := Read(fileSystem, "input.yaml", DefaultOptions()); err == nil {
			t.Fatal("Read() ignored a filesystem failure")
		}
	}
	if got, ok := fault.CategoryOf(&parseError{}); !ok || got != fault.InvalidInput {
		t.Errorf("CategoryOf() = %v, %v, want invalid-input", got, ok)
	}
	if Diagnostics(errors.New("other")) != nil {
		t.Fatal("Diagnostics() invented a source error")
	}
}

func checkBudgetCase(t *testing.T, configure func(*Limits), run func(*Budget) error) {
	t.Helper()
	limits := DefaultLimits()
	configure(&limits)
	budget, err := NewBudget(limits)
	if err != nil {
		t.Fatal(err)
	}
	err = run(budget)
	ds := Diagnostics(err)
	if len(ds) != 1 || ds[0].Code != "sdl.import.budget-exceeded" {
		t.Errorf("budget error = %v, diagnostics %+v", err, ds)
	}
}
