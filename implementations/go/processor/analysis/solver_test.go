package analysis

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func requireOperational(t *testing.T, err error) {
	t.Helper()
	if category, ok := fault.CategoryOf(err); !ok || category != fault.Operational {
		t.Fatalf("got %v, want an operational error", err)
	}
}

func TestSolverRejectsUnadmittedExecutable(t *testing.T) {
	for _, name := range []string{"", "z3", filepath.Join(t.TempDir(), "missing")} {
		_, err := OpenSolver(name)
		requireOperational(t, err)
	}
	path := filepath.Join(t.TempDir(), "z3")
	if err := os.WriteFile(path, []byte("private input must not appear in errors"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := OpenSolver(path)
	requireOperational(t, err)
	if err.Error() != "operational: solver-identity" {
		t.Fatal(err)
	}
}

func TestSolverBudgetBoundaryAndUnknown(t *testing.T) {
	elapsed := time.Duration(0)
	budget := solverBudget{elapsed: func() time.Duration { return elapsed }, maxChecks: 1}
	if timeout, err := budget.consume(); err != nil || timeout != 5000 {
		t.Fatalf("%d, %v", timeout, err)
	}
	_, err := budget.consume()
	requireOperational(t, err)
	budget.used = 0
	elapsed = 5*time.Second - time.Nanosecond
	if timeout, consumeErr := budget.consume(); consumeErr != nil || timeout != 1 {
		t.Fatalf("%d, %v", timeout, consumeErr)
	}
	elapsed = 5 * time.Second
	requireOperational(t, budget.checkpoint())
	budget.elapsed = func() time.Duration { return 0 }
	budget.used = 0
	_, err = boundedCheck(&budget, func(int) (string, error) { return "unknown", nil })
	requireOperational(t, err)
	budget.used = 0
	_, err = boundedCheck(&budget, func(int) (string, error) {
		budget.elapsed = func() time.Duration { return 5 * time.Second }
		return "sat", nil
	})
	requireOperational(t, err)
}

func TestSolverPublishedMaximumHasFiniteCheckBudget(t *testing.T) {
	model := constraintModel{Symbols: make([]constraintSymbol, 128), Clauses: make([]constraintClause, 512)}
	for index := range model.Symbols {
		model.Symbols[index].Domain = make([]any, 256)
	}
	budget := solverBudget{elapsed: func() time.Duration { return 0 }, maxChecks: solverCheckLimit(model)}
	if budget.maxChecks != 32769 {
		t.Fatalf("published maximum check budget = %d", budget.maxChecks)
	}
	for range 32769 {
		if _, err := budget.consume(); err != nil {
			t.Fatal(err)
		}
	}
	_, err := budget.consume()
	requireOperational(t, err)
}

func TestCanonicalSolverSelectionAndCore(t *testing.T) {
	model := constraintModel{Symbols: []constraintSymbol{{ID: "x", Variable: "choice", Domain: []any{false, true}}}, Clauses: []constraintClause{{ID: "a", Symbol: "x", Allowed: []any{true}}, {ID: "b", Symbol: "x", Allowed: []any{false}}}}
	checks := 0
	check := func(active []string, _ map[string]int, _ int) (string, error) {
		checks++
		if len(active) == 2 {
			return "unsat", nil
		}
		return "sat", nil
	}
	got, err := selectSolution(model, &solverBudget{elapsed: func() time.Duration { return 0 }, maxChecks: 3}, check)
	if err != nil || !cmp.Equal(got.core, []string{"a", "b"}) || checks != 3 {
		t.Fatalf("%+v %d %v", got, checks, err)
	}
	model.Clauses = model.Clauses[:1]
	check = func(_ []string, fixed map[string]int, _ int) (string, error) {
		if n, ok := fixed["x"]; ok && n == 0 {
			return "unsat", nil
		}
		return "sat", nil
	}
	got, err = selectSolution(model, &solverBudget{elapsed: func() time.Duration { return 0 }, maxChecks: 3}, check)
	if err != nil || !cmp.Equal(got.assignment, map[string]any{"choice": true}) {
		t.Fatalf("%+v %v", got, err)
	}
}

func TestSolverDuplicateClauseFailsBeforeCheck(t *testing.T) {
	model := constraintModel{Clauses: []constraintClause{{ID: "same"}, {ID: "same"}}}
	_, err := selectSolution(model, &solverBudget{elapsed: func() time.Duration { return 0 }, maxChecks: 3}, func([]string, map[string]int, int) (string, error) {
		t.Fatal("duplicate reached solver")
		return "", nil
	})
	requireOperational(t, err)
}

// Covers the incumbent initial-decision, core-reduction and witness-selection
// unknown regressions, including a solver that contradicts its first answer.
func TestSolverSelectionRefusesIncompleteAndInconsistentAnswers(t *testing.T) {
	model := constraintModel{Symbols: []constraintSymbol{{ID: "x", Variable: "choice", Domain: []any{false, true}}}, Clauses: []constraintClause{{ID: "a", Symbol: "x", Allowed: []any{true}}}}
	for _, answers := range [][]string{{"unknown"}, {"unsat", "unknown"}, {"sat", "unknown"}, {"sat", "unsat", "unsat"}} {
		calls := 0
		got, err := selectSolution(model, &solverBudget{elapsed: func() time.Duration { return 0 }, maxChecks: 3}, func([]string, map[string]int, int) (string, error) {
			if calls >= len(answers) {
				t.Fatal("probe continued after refusal")
			}
			answer := answers[calls]
			calls++
			return answer, nil
		})
		requireOperational(t, err)
		if got.assignment != nil || got.core != nil || calls != len(answers) {
			t.Fatalf("partial evidence escaped refusal: %+v, checks=%d", got, calls)
		}
	}
}

func TestSolverModelConstructionAndSelectionShareDeadline(t *testing.T) {
	model := constraintModel{Symbols: []constraintSymbol{{ID: "x", Domain: []any{false, true}}}, Clauses: []constraintClause{{ID: "a", Symbol: "x", Allowed: []any{true}}}}
	ticks := 0
	budget := &solverBudget{elapsed: func() time.Duration {
		ticks++
		if ticks > 1 {
			return solverTimeout
		}
		return 0
	}, maxChecks: 3}
	_, err := modelScript(model, budget)
	requireOperational(t, err)
	// The final checkpoint must reject selection that finishes at the deadline,
	// even when its last solver check returned just before it.
	ticks = 0
	budget.elapsed = func() time.Duration {
		ticks++
		if ticks == 4 {
			return solverTimeout
		}
		return 0
	}
	_, err = selectSolution(constraintModel{}, budget, func([]string, map[string]int, int) (string, error) { return "sat", nil })
	requireOperational(t, err)
}

func TestAdmittedNativeSolver(t *testing.T) {
	path := os.Getenv("RAES_TEST_Z3")
	if path == "" {
		t.Skip("explicit admitted executable required")
	}
	solver, err := OpenSolver(path)
	if err != nil {
		t.Fatal(err)
	}
	model := constraintModel{Symbols: []constraintSymbol{{ID: "x", Variable: "choice", Domain: []any{false, 1, "one"}}}, Clauses: []constraintClause{{ID: "a", Symbol: "x", Allowed: []any{1, "one"}}}}
	got, err := solver.solve(context.Background(), model)
	if err != nil || !cmp.Equal(got.assignment, map[string]any{"choice": 1}) {
		t.Fatalf("%+v %v", got, err)
	}
	model.Clauses = append(model.Clauses, constraintClause{ID: "b", Symbol: "x", Allowed: []any{true}})
	got, err = solver.solve(context.Background(), model)
	if err != nil || !cmp.Equal(got.core, []string{"b"}) {
		t.Fatalf("%+v %v", got, err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = solver.solve(ctx, model)
	requireOperational(t, err)
}

func TestSolverRejectsWritableExecutable(t *testing.T) {
	path := os.Getenv("RAES_TEST_Z3")
	if path == "" {
		t.Skip("explicit admitted executable required")
	}
	copied := filepath.Join(t.TempDir(), "z3")
	if err := os.WriteFile(copied, readTestFile(t, path), 0600); err != nil { //nolint:gosec // Destination is a fixed filename inside this test's private directory.
		t.Fatal(err)
	}
	if err := os.Chmod(copied, 0700); err != nil { //nolint:gosec // Deliberately writable executable exercises the rejection boundary.
		t.Fatal(err)
	}
	_, err := OpenSolver(copied)
	requireOperational(t, err)
}

func TestNativeSolverMatchesExhaustiveFiniteReference(t *testing.T) {
	path := os.Getenv("RAES_TEST_Z3")
	if path == "" {
		t.Skip("explicit admitted executable required")
	}
	solver, err := OpenSolver(path)
	if err != nil {
		t.Fatal(err)
	}
	// Enumerate every allowed subset for each of two Boolean domains.
	// The oracle uses a direct finite assignment scan, independent of SMT text
	// construction, incremental checks and canonical witness selection.
	for left := range 4 {
		for right := range 4 {
			t.Run(fmt.Sprintf("%d-%d", left, right), func(t *testing.T) {
				checkFiniteSolverReference(t, solver, left, right)
			})
		}
	}
}

func checkFiniteSolverReference(t *testing.T, solver *Solver, left, right int) {
	t.Helper()
	model := constraintModel{}
	for index, mask := range []int{left, right} {
		id := fmt.Sprintf("x%d", index)
		domain := []any{false, true}
		model.Symbols = append(model.Symbols, constraintSymbol{ID: id, Variable: id, Domain: domain})
		allowed := []any{}
		for bit, value := range domain {
			if mask&(1<<bit) != 0 {
				allowed = append(allowed, value)
			}
		}
		model.Clauses = append(model.Clauses, constraintClause{ID: fmt.Sprintf("c%d", index), Symbol: id, Allowed: allowed})
	}
	got, err := solver.solve(t.Context(), model)
	if err != nil {
		t.Fatal(err)
	}
	want := finiteBooleanWitness(left, right)
	if want != nil {
		if !cmp.Equal(want, got.assignment) || got.core != nil {
			t.Fatalf("finite witness mismatch: %+v, want %v", got, want)
		}
		return
	}
	// Sorted deletion retains the last empty-domain clause when both conflict.
	core := []string{"c0"}
	if right == 0 {
		core = []string{"c1"}
	}
	if got.assignment != nil || !cmp.Equal(got.core, core) {
		t.Fatalf("finite core mismatch: %+v, want %v", got, core)
	}
}

func finiteBooleanWitness(left, right int) map[string]any {
	for x := range 2 {
		for y := range 2 {
			if left&(1<<x) != 0 && right&(1<<y) != 0 {
				return map[string]any{"x0": x == 1, "x1": y == 1}
			}
		}
	}
	return nil
}
