package experiment

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type closingReader struct {
	closed chan struct{}
	count  int
	fail   bool
}

func (r *closingReader) Close() error {
	r.count++
	if r.count == 1 {
		close(r.closed)
	}
	if r.fail {
		return errors.New("private-close-message")
	}
	return nil
}

type evidenceProvider func(context.Context, binding.ExperimentRunV1) (EvidenceInputs, error)

func (f evidenceProvider) Open(ctx context.Context, run binding.ExperimentRunV1) (EvidenceInputs, error) {
	return f(ctx, run)
}

type timeoutCalls struct{}

func (timeoutCalls) Call(ctx context.Context, _ string, _ time.Duration, work func(context.Context) (any, error)) (any, error) {
	ctx, cancel := context.WithTimeout(ctx, time.Millisecond)
	defer cancel()
	result := make(chan error, 1)
	go func() { _, err := work(ctx); result <- err }()
	select {
	case err := <-result:
		return struct{}{}, err
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}
func TestRuntimeClosesEvidenceReadersOnRejectionAndLateCompletion(t *testing.T) {
	for _, late := range []bool{false, true} {
		t.Run(map[bool]string{false: "rejection", true: "late-completion"}[late], func(t *testing.T) { checkReaderClosure(t, late) })
	}
}
func TestRuntimeClosesAllReadersWhenOneCloseFails(t *testing.T) {
	a := &closingReader{closed: make(chan struct{}), fail: true}
	b := &closingReader{closed: make(chan struct{})}
	if err := closeReaders(context.Background(), []io.Closer{a, a, b}); err == nil {
		t.Fatal("close failure ignored")
	}
	if a.count != 1 || b.count != 1 {
		t.Fatal("closure stopped before all readers")
	}
}

func checkReaderClosure(t *testing.T, late bool) {
	t.Helper()

	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	ref := recordReferences(t).Cases[3]
	source := recordSourceFixture(t, c, ref)
	var run binding.ExperimentRunV1
	if convert(ref.Run, &run) != nil {
		t.Fatal("fixture")
	}
	stream := &closingReader{closed: make(chan struct{})}
	release := make(chan struct{})
	reader := evidenceProvider(func(context.Context, binding.ExperimentRunV1) (EvidenceInputs, error) {
		if late {
			<-release
		}
		return EvidenceInputs{Readers: []io.Closer{stream, stream}}, errors.New("private-open-message")
	})
	if late {
		c.options.Calls = timeoutCalls{}
	}
	err := c.validateRun(context.Background(), source, run, reader)
	if err == nil || strings.Contains(err.Error(), "private-") {
		t.Fatal("unsafe evidence failure", err)
	}
	if late {
		close(release)
	}
	select {
	case <-stream.closed:
	case <-time.After(time.Second):
		t.Fatal("reader leaked")
	}
	if stream.count != 1 {
		t.Fatal("reader closed more than once")
	}
}
