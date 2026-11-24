package sdl

import (
	"errors"
	"io/fs"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

func TestCapturedSourceFilesFreezeSuppliedBytesAndReportMetadata(t *testing.T) {
	input := []byte("abc")
	s := contextSources{supplied: map[string][]byte{"nested/source.sdl": input}, limits: DefaultLimits(), files: map[string][]byte{}}
	file, err := s.Open("nested/source.sdl")
	if err != nil {
		t.Fatal(err)
	}
	input[0] = 'z'
	raw, err := fs.ReadFile(&s, "nested/source.sdl")
	if err != nil || string(raw) != "abc" {
		t.Fatalf("source bytes were not frozen: %q %v", raw, err)
	}
	checkCapturedSourceMetadata(t, file)
	for _, stat := range []func(string) (fs.FileInfo, error){s.Stat, s.Lstat} {
		if capturedInfo, statErr := stat("nested/source.sdl"); statErr != nil || capturedInfo.Size() != 3 {
			t.Fatalf("retained source stat failed: %v", statErr)
		}
	}
	info, err := s.Stat("nested")
	if err != nil || !info.IsDir() || info.Mode() != fs.ModeDir|0500 {
		t.Fatalf("supplied directory metadata invalid: %v %v", info, err)
	}
	checkCapturedSourceDenials(t, &s)
}

func checkCapturedSourceDenials(t *testing.T, s *contextSources) {
	t.Helper()
	for _, name := range []string{"../escape", "missing"} {
		if _, err := s.Open(name); err == nil {
			t.Fatalf("invalid or missing source opened: %q", name)
		}
		if _, err := s.Stat(name); err == nil {
			t.Fatalf("invalid or missing source stat succeeded: %q", name)
		}
		if _, err := s.ReadLink(name); err == nil {
			t.Fatalf("source-only context granted link authority: %q", name)
		}
	}
}

func checkCapturedSourceMetadata(t *testing.T, file fs.File) {
	t.Helper()
	info, err := file.Stat()
	if err != nil || info.Name() != "source.sdl" || info.Size() != 3 || info.IsDir() || info.Mode() != 0400 || !info.ModTime().IsZero() || info.Sys() != nil {
		t.Fatalf("invalid captured metadata: %v %v", info, err)
	}
	if file.Close() != nil {
		t.Fatal("captured file close failed")
	}
}

func TestSourceCaptureRetainsOnlyRegularFilesWithinSharedBudget(t *testing.T) {
	limits := DefaultLimits()
	limits.MaxInputBytes = 4
	limits.MaxComposedBytes = 5
	s := contextSources{provider: fstest.MapFS{"first": {Data: []byte("abc")}, "second": {Data: []byte("def")}, "large": {Data: []byte("12345")}, "directory": {Mode: fs.ModeDir}}, limits: limits, files: map[string][]byte{}}
	if _, err := s.Open("first"); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"second", "large", "directory", "missing"} {
		if _, err := s.Open(name); err == nil {
			t.Fatalf("invalid capture admitted: %q", name)
		}
	}
	if s.used != 3 || len(s.files) != 1 {
		t.Fatal("refused source consumed budget or was retained")
	}
	if s.retain("first", []byte("x")) == nil || s.retain("../bad", nil) == nil {
		t.Fatal("capture replaced a source or retained an invalid path")
	}
	if _, err := s.Stat("missing"); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("provider stat error lost: %v", err)
	}
	if _, err := s.Lstat("missing"); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("provider lstat error lost: %v", err)
	}
	empty := contextSources{limits: limits, files: map[string][]byte{}}
	if _, err := empty.Open("missing"); !errors.Is(err, fs.ErrNotExist) {
		t.Fatal("empty context gained filesystem access")
	}
}

func TestSourceContextLocksAndPhaseFacadesKeepNativeAuthority(t *testing.T) {
	lock, err := module.DecodeLockfile([]byte(`{}`))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := lockBytes(lock)
	if err != nil {
		t.Fatal(err)
	}
	if _, decodeErr := module.DecodeLockfile(raw); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	lock.SchemaVersion = "future"
	if _, lockErr := lockBytes(lock); lockErr == nil {
		t.Fatal("unknown lock version accepted")
	}
	if _, captureErr := captureSourceContext(SourceContext{Root: "source.sdl", RootBytes: []byte("x"), Lock: &lock}, DefaultParseOptions()); captureErr == nil {
		t.Fatal("invalid supplied lock retained")
	}
	lock, err = module.DecodeLockfile([]byte(`{}`))
	if err != nil {
		t.Fatal(err)
	}
	captured, err := captureSourceContext(SourceContext{Root: "source.sdl", RootBytes: []byte("name: example\n"), Lock: &lock}, DefaultParseOptions())
	if err != nil || len(captured.files) != 2 {
		t.Fatalf("valid lock not captured: %v", err)
	}
}

func TestNativePhaseFacadesKeepTheirIssuingOwner(t *testing.T) {
	var registry *module.Registry
	if _, err := sourceTrustRegistry(registry); err == nil {
		t.Fatal("typed nil registry granted authority")
	}
	scenario, err := Parse([]byte("name: example\n"), DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	family, err := AdmitFamily(scenario)
	if err != nil {
		t.Fatal(err)
	}
	instance, err := Instantiate(family, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := AdmitInstantiated(instance); err != nil {
		t.Fatalf("native concrete phase refused: %v", err)
	}
	if _, err := AdmitInstantiated(family); err == nil {
		t.Fatal("family acquired concrete provenance")
	}
	if _, err := AdmitFamily(nil); err == nil {
		t.Fatal("nil family owner accepted")
	}
	if _, err := AdmitInstantiated(nil); err == nil {
		t.Fatal("nil concrete owner accepted")
	}
}
