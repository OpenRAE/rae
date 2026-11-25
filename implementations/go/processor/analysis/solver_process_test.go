package analysis

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func TestSolverChild(_ *testing.T) {
	mode := os.Getenv("RAES_SOLVER_HELPER")
	if mode == "" {
		return
	}
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.Contains(line, "get-info") && mode == "version" {
			_, _ = fmt.Fprintln(os.Stdout, `(:version "0.0.0")`)
		} else if strings.Contains(line, "get-info") {
			_, _ = fmt.Fprintln(os.Stdout, `(:version "4.16.0")`)
		}
		if strings.Contains(line, "check-sat-assuming") {
			switch mode {
			case "oversize":
				_, _ = fmt.Fprintln(os.Stdout, strings.Repeat("x", 1024))
			case "unknown":
				_, _ = fmt.Fprintln(os.Stdout, "unknown")
			case "hang":
				time.Sleep(time.Hour)
			}
		}
	}
	os.Exit(0)
}

func TestSolverProcessBoundAndCollection(t *testing.T) {
	for _, mode := range []string{"oversize", "unknown", "hang"} {
		t.Run(mode, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			cmd := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestSolverChild$") //nolint:gosec // Runs only this test executable with a fixed helper selector.
			cmd.Env = []string{"RAES_SOLVER_HELPER=" + mode}
			session, err := startSolverCommand(cmd, cancel)
			if err != nil {
				t.Fatal(err)
			}
			_, err = boundedCheck(&solverBudget{elapsed: func() time.Duration { return 0 }, maxChecks: 1}, func(timeout int) (string, error) { return session.check(nil, nil, timeout) })
			requireOperational(t, err)
			session.close()
			if cmd.ProcessState == nil {
				t.Fatal("child was not collected")
			}
		})
	}
}

func TestSolverProcessStartRefusals(t *testing.T) {
	if _, err := (*Solver)(nil).start(t.Context()); err == nil {
		t.Fatal("got nil error, want a missing solver refused")
	}
	cancelled, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := (&Solver{path: "/missing"}).start(cancelled); err == nil {
		t.Fatal("got nil error, want a cancelled start refused")
	}
	if _, err := (&Solver{path: "/missing"}).start(t.Context()); err == nil {
		t.Fatal("got nil error, want an unadmitted executable refused")
	}
	child := func(mode string) *exec.Cmd {
		cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=^TestSolverChild$") //nolint:gosec // Runs only this test executable with a fixed helper selector.
		cmd.Env = []string{"RAES_SOLVER_HELPER=" + mode}
		return cmd
	}
	presetInput := child("version")
	presetInput.Stdin = strings.NewReader("")
	presetOutput := child("version")
	presetOutput.Stdout = &strings.Builder{}
	for name, cmd := range map[string]*exec.Cmd{
		"wrong version":   child("version"),
		"preset input":    presetInput,
		"preset output":   presetOutput,
		"missing program": exec.CommandContext(t.Context(), "/nonexistent/raes-solver"),
	} {
		t.Run(name, func(t *testing.T) {
			_, cancel := context.WithCancel(t.Context())
			_, err := startSolverCommand(cmd, cancel)
			requireOperational(t, err)
		})
	}
}

func TestSolverDiagnosticsStayBounded(t *testing.T) {
	sink := &boundedDiscard{remaining: 2}
	if count, err := sink.Write([]byte("ab")); err != nil || count != 2 {
		t.Fatalf("got %d, %v, want the bounded write accepted", count, err)
	}
	if _, err := sink.Write([]byte("c")); err == nil {
		t.Fatal("got nil error, want the overflow refused")
	}
}
