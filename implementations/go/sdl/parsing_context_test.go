package sdl_test

import (
	"context"
	"errors"
	"io/fs"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type cancellationFS struct {
	files  fstest.MapFS
	opens  int
	cancel context.CancelFunc
}

func (files *cancellationFS) Open(name string) (fs.File, error) {
	files.opens++
	file, err := files.files.Open(name)
	if err != nil {
		return nil, err
	}
	if files.cancel != nil {
		return &cancellationFile{File: file, cancel: files.cancel}, nil
	}
	return file, nil
}

type cancellationFile struct {
	fs.File

	cancel context.CancelFunc
}

func (file *cancellationFile) Read(buffer []byte) (int, error) {
	n, err := file.File.Read(buffer)
	file.cancel()
	return n, err
}

func TestParsingCancellationPrecedesSourceReads(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	files := &cancellationFS{files: fstest.MapFS{"input.yaml": &fstest.MapFile{Data: []byte("name: example\n")}}}
	options := sdl.DefaultParseOptions()
	if _, err := sdl.ParseWithContext(ctx, []byte("name: example\n"), options); !errors.Is(err, context.Canceled) {
		t.Fatalf("byte parsing ignored cancellation: %v", err)
	}
	if _, err := sdl.ParseFileWithContext(ctx, files, "input.yaml", options); !errors.Is(err, context.Canceled) {
		t.Fatalf("file parsing ignored cancellation: %v", err)
	}
	if _, err := sdl.ParseSourceWithContext(ctx, sdl.SourceContext{Root: "input.yaml", FS: files}, options); !errors.Is(err, context.Canceled) {
		t.Fatalf("source parsing ignored cancellation: %v", err)
	}
	if files.opens != 0 {
		t.Fatal("canceled parsing read the source")
	}
}

func TestParsingCancellationDuringReadPreventsPublication(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	files := &cancellationFS{files: fstest.MapFS{"input.yaml": &fstest.MapFile{Data: []byte("name: example\n")}}, cancel: cancel}
	scenario, err := sdl.ParseFileWithContext(ctx, files, "input.yaml", sdl.DefaultParseOptions())
	if !errors.Is(err, context.Canceled) || scenario != nil {
		t.Fatalf("published after cancellation: %v", err)
	}
	if files.opens != 1 {
		t.Fatalf("source opened %d times", files.opens)
	}
}

func TestParsingContextRequiresExplicitNonNilContext(t *testing.T) {
	_, err := sdl.ParseWithContext(nil, []byte("name: example\n"), sdl.DefaultParseOptions()) //nolint:staticcheck // This case verifies refusal of an invalid nil caller context.
	category, known := fault.CategoryOf(err)
	if !known || category != fault.InvalidInput {
		t.Fatalf("nil context accepted: %v", err)
	}
	scenario, err := sdl.ParseWithContext(t.Context(), []byte("name: example\n"), sdl.DefaultParseOptions())
	if err != nil || !scenario.SemanticallyValidated() {
		t.Fatalf("active context refused: %v", err)
	}
}
