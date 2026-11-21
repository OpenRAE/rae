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
		if strings.Contains(line, "get-info") {
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
