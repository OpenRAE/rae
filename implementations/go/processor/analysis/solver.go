// Package analysis owns bounded processor analysis and its evidence.
package analysis

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

const solverTimeout = 5 * time.Second

// Solver selects an explicitly admitted Z3 executable. Each request starts a
// separate process; no mutable solver state is shared between requests.
type Solver struct{ path string }

type constraintSymbol struct {
	Sort     string `json:"sort"`
	ID       string `json:"symbol_id"`
	Variable string `json:"variable"`
	Domain   []any  `json:"domain"`
}
type constraintClause struct {
	Kind    string `json:"kind"`
	Address string `json:"source_address"`
	ID      string `json:"clause_id"`
	Symbol  string `json:"symbol_id"`
	Allowed []any  `json:"allowed_values"`
}
type constraintModel struct {
	Profile        string             `json:"profile"`
	Theory         string             `json:"theory_profile"`
	Translation    string             `json:"translation_profile"`
	SourceDigest   string             `json:"source_digest"`
	AuthoredDigest map[string]any     `json:"authored_digest"`
	Symbols        []constraintSymbol `json:"symbols"`
	Clauses        []constraintClause `json:"clauses"`
}
type solverResult struct {
	assignment map[string]any
	core       []string
}
type solverBudget struct {
	elapsed         func() time.Duration
	maxChecks, used int
}

func solverError(code string) error { return fault.New(fault.Operational, "solver-"+code, nil) }
func (b *solverBudget) checkpoint() error {
	if b.elapsed() >= solverTimeout {
		return solverError("deadline")
	}
	return nil
}
func (b *solverBudget) consume() (int, error) {
	if err := b.checkpoint(); err != nil {
		return 0, err
	}
	if b.used >= b.maxChecks {
		return 0, solverError("check-budget")
	}
	b.used++
	remaining := solverTimeout - b.elapsed()
	if remaining <= 0 {
		return 0, solverError("deadline")
	}
	return int((remaining + time.Millisecond - 1) / time.Millisecond), nil
}
func boundedCheck(b *solverBudget, check func(int) (string, error)) (string, error) {
	timeout, err := b.consume()
	if err != nil {
		return "", err
	}
	result, err := check(timeout)
	if err != nil {
		return "", err
	}
	if err = b.checkpoint(); err != nil {
		return "", err
	}
	if result != solverSat && result != "unsat" {
		return "", solverError("incomplete")
	}
	return result, nil
}

type solverCheck func([]string, map[string]int, int) (string, error)

func selectSolution(model constraintModel, budget *solverBudget, check solverCheck) (solverResult, error) {
	all := make([]string, 0, len(model.Clauses))
	seen := map[string]bool{}
	for _, clause := range model.Clauses {
		if seen[clause.ID] {
			return solverResult{}, solverError("duplicate-clause")
		}
		seen[clause.ID] = true
		all = append(all, clause.ID)
	}
	probe := func(active []string, fixed map[string]int) (string, error) {
		return boundedCheck(budget, func(timeout int) (string, error) { return check(active, fixed, timeout) })
	}
	initial, err := probe(all, nil)
	if err != nil {
		return solverResult{}, err
	}
	var result solverResult
	if initial == solverSat {
		result, err = selectWitness(model, all, probe)
	} else {
		result, err = reduceCore(all, probe)
	}
	if err != nil {
		return solverResult{}, err
	}
	return result, budget.checkpoint()
}

type solutionProbe func([]string, map[string]int) (string, error)

func selectWitness(model constraintModel, all []string, probe solutionProbe) (solverResult, error) {
	fixed := map[string]int{}
	result := solverResult{assignment: map[string]any{}}
	for _, symbol := range model.Symbols {
		index, err := selectDomainValue(symbol, all, fixed, probe)
		if err != nil {
			return solverResult{}, err
		}
		result.assignment[symbol.Variable] = symbol.Domain[index]
	}
	return result, nil
}
func selectDomainValue(symbol constraintSymbol, all []string, fixed map[string]int, probe solutionProbe) (int, error) {
	for index := range symbol.Domain {
		fixed[symbol.ID] = index
		outcome, err := probe(all, fixed)
		if err != nil {
			return 0, err
		}
		if outcome == solverSat {
			return index, nil
		}
	}
	return 0, solverError(termWitness)
}
func reduceCore(all []string, probe solutionProbe) (solverResult, error) {
	core := slices.Clone(all)
	for _, id := range all {
		candidate := slices.DeleteFunc(slices.Clone(core), func(current string) bool { return current == id })
		outcome, err := probe(candidate, nil)
		if err != nil {
			return solverResult{}, err
		}
		if outcome == "unsat" {
			core = candidate
		}
	}
	slices.Sort(core)
	return solverResult{core: core}, nil
}

func smtName(value string) string { return fmt.Sprintf("raes_%x", []byte(value)) }
func modelScript(model constraintModel, budget *solverBudget) (string, error) {
	if len(model.Symbols) > 128 || len(model.Clauses) > 512 {
		return "", solverError("model-bound")
	}
	var script strings.Builder
	script.WriteString("(set-option :print-success false)\n(set-option :auto_config false)\n(set-option :produce-models true)\n(set-option :produce-unsat-cores true)\n(set-option :smt.random_seed 0)\n(set-option :smt.threads 1)\n(set-option :timeout 5000)\n(set-logic QF_LIA)\n")
	symbols := map[string]constraintSymbol{}
	identities := map[string]bool{}
	for _, symbol := range model.Symbols {
		if identities[symbol.ID] || len(symbol.Domain) > 256 || len(symbol.ID) > 4096 {
			return "", solverError("model-identity")
		}
		identities[symbol.ID] = true
		symbols[symbol.ID] = symbol
		fmt.Fprintf(&script, "(declare-const %s Int)\n", smtName(symbol.ID))
	}
	for _, clause := range model.Clauses {
		symbol, ok := symbols[clause.Symbol]
		if !ok || identities[clause.ID] || len(clause.ID) > 4096 || len(clause.Allowed) > 256 {
			return "", solverError("model-identity")
		}
		identities[clause.ID] = true
		tracker := smtName(clause.ID)
		fmt.Fprintf(&script, "(declare-const %s Bool)\n(assert (=> %s (or false", tracker, tracker)
		if err := writeAllowedDomain(&script, symbol, clause.Allowed, budget); err != nil {
			return "", err
		}
		script.WriteString(")))\n")
	}
	return script.String(), budget.checkpoint()
}
func (s *Solver) solve(ctx context.Context, model constraintModel) (solverResult, error) {
	if ctx == nil {
		return solverResult{}, solverError("cancelled")
	}
	ctx, cancel := context.WithTimeout(ctx, solverTimeout)
	defer cancel()
	budget := &solverBudget{elapsed: clock.StartElapsed()}
	budget.maxChecks = solverCheckLimit(model)
	script, err := modelScript(model, budget)
	if err != nil {
		return solverResult{}, err
	}
	session, err := s.start(ctx)
	if err != nil {
		return solverResult{}, err
	}
	defer session.close()
	if err = session.write(script); err != nil {
		return solverResult{}, err
	}
	return selectSolution(model, budget, session.check)
}

func solverCheckLimit(model constraintModel) int {
	members := 0
	for _, symbol := range model.Symbols {
		members += len(symbol.Domain)
	}
	return 1 + max(members, len(model.Clauses))
}

func sameScalar(a, b any) bool {
	switch a.(type) {
	case string, bool, int, int64, json.Number:
		switch b.(type) {
		case string, bool, int, int64, json.Number:
			return a == b
		}
	}
	return false
}

func writeAllowedDomain(script *strings.Builder, symbol constraintSymbol, allowed []any, budget *solverBudget) error {
	for index, value := range symbol.Domain {
		if slices.ContainsFunc(allowed, func(candidate any) bool { return sameScalar(value, candidate) }) {
			fmt.Fprintf(script, " (= %s %d)", smtName(symbol.ID), index)
		}
		if err := budget.checkpoint(); err != nil {
			return err
		}
	}
	return nil
}
