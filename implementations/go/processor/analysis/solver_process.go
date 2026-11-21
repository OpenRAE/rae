package analysis

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

const solverExecutableSize int64 = 34954456
const solverExecutableDigest = "sha256:e583c4186a45e72411fa2cb2048401eed03f0f8e5f24694676a8f6271a50b765"

// OpenSolver admits the pinned executable on the qualified Linux/amd64 host.
// The identity is checked again through the open executable on every request.
func OpenSolver(path string) (*Solver, error) {
	file, err := admitExecutable(path)
	if err != nil {
		return nil, err
	}
	if err = file.Close(); err != nil {
		return nil, solverError(termIdentity)
	}
	return &Solver{path: path}, nil
}
func admitExecutable(path string) (*os.File, error) {
	if runtime.GOOS != "linux" || runtime.GOARCH != "amd64" || !filepath.IsAbs(path) {
		return nil, solverError(termIdentity)
	}
	file, err := os.Open(path) //nolint:gosec // Caller selects the path; byte size, digest, host and permissions are verified on this descriptor.
	if err != nil {
		return nil, solverError(termIdentity)
	}
	valid := false
	defer func() {
		if !valid {
			_ = file.Close()
		}
	}()
	state, err := file.Stat()
	if err != nil || !state.Mode().IsRegular() || state.Size() != solverExecutableSize || state.Mode().Perm()&0222 != 0 || state.Mode().Perm()&0100 == 0 {
		return nil, solverError(termIdentity)
	}
	data, err := io.ReadAll(io.LimitReader(file, solverExecutableSize+1))
	if err != nil || int64(len(data)) != solverExecutableSize || digest.SHA256(data) != solverExecutableDigest {
		return nil, solverError(termIdentity)
	}
	valid = true
	return file, nil
}

type solverSession struct {
	command *exec.Cmd
	cancel  context.CancelFunc
	input   io.WriteCloser
	output  *bufio.Scanner
}

// A bounded writer prevents a malfunctioning child from accumulating diagnostics.
// Its contents are discarded and are never part of an operational error.
type boundedDiscard struct{ remaining int }

func (d *boundedDiscard) Write(p []byte) (int, error) {
	if len(p) > d.remaining {
		return 0, solverError("response-bound")
	}
	d.remaining -= len(p)
	return len(p), nil
}

func (s *Solver) start(parent context.Context) (*solverSession, error) {
	if s == nil || parent == nil || parent.Err() != nil {
		return nil, solverError("cancelled")
	}
	executable, err := admitExecutable(s.path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = executable.Close() }()
	ctx, cancel := context.WithTimeout(parent, solverTimeout)
	// Pass the verified open file, so replacing its pathname cannot select other bytes.
	cmd := exec.CommandContext(ctx, "/proc/self/fd/3", "-in", "-smt2")
	cmd.ExtraFiles = []*os.File{executable}
	cmd.Env = []string{"LANG=C", "LC_ALL=C"}
	return startSolverCommand(cmd, cancel)
}

func startSolverCommand(cmd *exec.Cmd, cancel context.CancelFunc) (*solverSession, error) {
	cmd.WaitDelay = 100 * time.Millisecond
	cmd.Stderr = &boundedDiscard{remaining: 4096}
	input, err := cmd.StdinPipe()
	if err != nil {
		cancel()
		return nil, solverError(termProcess)
	}
	output, err := cmd.StdoutPipe()
	if err != nil {
		cancel()
		_ = input.Close()
		return nil, solverError(termProcess)
	}
	if err = cmd.Start(); err != nil {
		cancel()
		_ = input.Close()
		_ = output.Close()
		return nil, solverError(termProcess)
	}
	scanner := bufio.NewScanner(output)
	scanner.Buffer(make([]byte, 128), 128)
	session := &solverSession{command: cmd, cancel: cancel, input: input, output: scanner}
	if err = session.write("(get-info :version)\n"); err != nil {
		session.close()
		return nil, err
	}
	version, err := session.read()
	if err != nil || version != `(:version "4.16.0")` {
		session.close()
		return nil, solverError(termVersion)
	}
	return session, nil
}
func (s *solverSession) close() { s.cancel(); _ = s.input.Close(); _ = s.command.Wait() }
func (s *solverSession) write(value string) error {
	if _, err := io.WriteString(s.input, value); err != nil {
		return solverError("protocol")
	}
	return nil
}
func (s *solverSession) read() (string, error) {
	if !s.output.Scan() {
		return "", solverError("protocol")
	}
	return s.output.Text(), nil
}
func (s *solverSession) check(active []string, fixed map[string]int, timeout int) (string, error) {
	var script strings.Builder
	fmt.Fprintf(&script, "(set-option :timeout %d)\n(push)\n", timeout)
	keys := make([]string, 0, len(fixed))
	for key := range fixed {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	for _, key := range keys {
		fmt.Fprintf(&script, "(assert (= %s %d))\n", smtName(key), fixed[key])
	}
	script.WriteString("(check-sat-assuming (")
	for _, id := range active {
		script.WriteString(smtName(id))
		script.WriteByte(' ')
	}
	script.WriteString("))\n(pop)\n")
	if err := s.write(script.String()); err != nil {
		return "", err
	}
	return s.read()
}
