package admission

import (
	"errors"
	"io"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"
)

type experimentBoundaryFS struct {
	file            fs.File
	root            fs.FS
	openErr, dirErr error
}

func (s experimentBoundaryFS) Open(name string) (fs.File, error) {
	if s.openErr != nil {
		return nil, s.openErr
	}
	if s.file != nil {
		return s.file, nil
	}
	if s.root != nil {
		return s.root.Open(name)
	}
	return nil, fs.ErrNotExist
}
func (s experimentBoundaryFS) Stat(name string) (fs.FileInfo, error) {
	if s.root != nil {
		return fs.Stat(s.root, name)
	}
	if s.file != nil {
		return s.file.Stat()
	}
	if s.openErr != nil {
		return nil, s.openErr
	}
	return nil, fs.ErrNotExist
}
func (s experimentBoundaryFS) ReadDir(string) ([]fs.DirEntry, error) { return nil, s.dirErr }

type experimentBoundaryFile struct {
	fs.File

	reader       io.Reader
	statErr      error
	closed, read int
}

func (f *experimentBoundaryFile) Read(data []byte) (int, error) {
	n, err := f.reader.Read(data)
	f.read += n
	return n, err
}
func (f *experimentBoundaryFile) Close() error { f.closed++; return f.File.Close() }
func (f *experimentBoundaryFile) Stat() (fs.FileInfo, error) {
	if f.statErr != nil {
		return nil, f.statErr
	}
	return f.File.Stat()
}

func TestExperimentFileErrorsStayContainedAndStreamsStayBounded(t *testing.T) {
	var reference struct{ Cases []experimentYAMLReferenceCase }
	readFullReferenceJSON(t, "testdata/experiment-yaml-reference.json", &reference)
	for _, test := range []string{"exact", "stat", "read", "growing"} {
		t.Run(test, func(t *testing.T) {
			checkExperimentFileBoundary(t, test, reference.Cases[0].Text)
		})
	}
	for _, failure := range []error{fs.ErrNotExist, fs.ErrPermission} {
		if _, err := LoadExperiment(experimentBoundaryFS{openErr: failure}, "input.exp", nil); err == nil {
			t.Fatal("file open failure lost")
		}
		if _, err := DiscoverExperiments(experimentBoundaryFS{root: fstest.MapFS{"example.exp.yaml": {Data: []byte("x")}}, dirErr: failure}, "."); err == nil {
			t.Fatal("directory failure lost")
		}
	}
	if _, err := LoadExperiment(nil, "input.exp", nil); err == nil {
		t.Fatal("ambient source admitted")
	}
	if paths, err := DiscoverExperiments(fstest.MapFS{}, "missing"); err != nil || len(paths) != 0 {
		t.Fatal("missing optional directory did not produce an empty inventory", err)
	}
	if _, err := LoadExperiment(fstest.MapFS{}, "../input.exp", nil); err == nil {
		t.Fatal("uncontained source admitted")
	}
	if _, err := DiscoverExperiments(nil, "."); err == nil {
		t.Fatal("ambient discovery admitted")
	}
	if _, err := DiscoverExperiments(fstest.MapFS{}, "../"); err == nil {
		t.Fatal("uncontained discovery admitted")
	}
}

func checkExperimentFileBoundary(t *testing.T, test, sourceText string) {
	t.Helper()

	base, err := (fstest.MapFS{"input.exp": {Data: []byte(sourceText)}}).Open("input.exp")
	if err != nil {
		t.Fatal(err)
	}
	file := &experimentBoundaryFile{File: base, reader: strings.NewReader(sourceText)}
	switch test {
	case "stat":
		file.statErr = errors.New("private source location")
	case "read":
		file.reader = failedEvidenceReader{}
	case "growing":
		file.reader = strings.NewReader(strings.Repeat("x", experimentInputBytes*2))
	}
	_, err = LoadExperiment(experimentBoundaryFS{file: file}, "input.exp", nil)
	if (err == nil) != (test == "exact") {
		t.Fatal("file ingress admission", err)
	}
	if file.closed != 1 || file.read > experimentInputBytes+1 {
		t.Fatal("file was not closed or stream exceeded read bound", file.closed, file.read)
	}
	if err != nil && strings.Contains(err.Error(), "private") {
		t.Fatal("source error detail escaped")
	}
}
