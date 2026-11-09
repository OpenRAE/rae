package authoring

import (
	"fmt"
	"slices"
)

const selectionStateLimit = 100000
const (
	selectionUnknown byte = iota
	selectionFalse
	selectionTrue
)

type semanticSelectionGroup struct {
	members          []int
	minimum, maximum int
}
type semanticSelectionLiteral struct {
	variable int
	value    byte
}
type semanticSelectionSolver struct {
	variables []semanticSelectionVariable
	ids       map[semanticSelectionVariable]int
	groups    []semanticSelectionGroup
	clauses   [][2]semanticSelectionLiteral
	branch    []int
	remaining int
}

func (m *semanticModel) selectionSolver() *semanticSelectionSolver {
	solver := &semanticSelectionSolver{ids: map[semanticSelectionVariable]int{}, remaining: selectionStateLimit}
	for _, point := range m.variations {
		check := semanticVariationCheck{model: m, point: point}
		members, _ := check.members()
		if len(members) == 0 {
			continue
		}
		names := make([]string, 0, len(members))
		for name := range members {
			names = append(names, name)
		}
		slices.Sort(names)
		solver.addGroup(point, names)
	}
	for _, point := range m.variations {
		check := semanticVariationCheck{model: m, point: point}
		members, names := check.members()
		for _, name := range names {
			source := solver.ids[semanticSelectionVariable{point.name, name}]
			solver.addRelations(m, source, members[name].Requires, selectionTrue)
			solver.addRelations(m, source, members[name].Excludes, selectionFalse)
		}
	}
	solver.orderBranches()
	return solver
}
func (s *semanticSelectionSolver) addGroup(point semanticVariation, names []string) {
	group := semanticSelectionGroup{minimum: len(names), maximum: len(names)}
	if point.Kind == variationAlternativeKind {
		group.minimum, group.maximum = 1, 1
	}
	if point.Kind == "subset" {
		group.minimum = point.Minimum
		if point.Maximum != nil {
			group.maximum = *point.Maximum
		}
	}
	for _, name := range names {
		id := len(s.variables)
		variable := semanticSelectionVariable{point.name, name}
		s.ids[variable] = id
		s.variables = append(s.variables, variable)
		group.members = append(group.members, id)
	}
	s.groups = append(s.groups, group)
}
func (s *semanticSelectionSolver) addRelations(m *semanticModel, source int, relations []semanticSelectionRelation, value byte) {
	for _, relation := range relations {
		matches := m.variationMatches(relation.Point)
		if len(matches) != 1 {
			continue
		}
		point := m.variations[matches[0]].name
		for _, member := range relation.Members {
			if id, known := s.ids[semanticSelectionVariable{point, member}]; known {
				s.clauses = append(s.clauses, [2]semanticSelectionLiteral{{source, selectionFalse}, {id, value}})
			}
		}
	}
}
func (s *semanticSelectionSolver) orderBranches() {
	counts := make([]int, len(s.variables))
	for _, clause := range s.clauses {
		for _, literal := range clause {
			counts[literal.variable]++
		}
	}
	s.branch = make([]int, len(s.variables))
	for i := range s.branch {
		s.branch[i] = i
	}
	slices.SortFunc(s.branch, func(left, right int) int {
		if counts[left] != counts[right] {
			return counts[right] - counts[left]
		}
		a, b := s.variables[left], s.variables[right]
		if a.point < b.point || a.point == b.point && a.member < b.member {
			return -1
		}
		if a == b {
			return 0
		}
		return 1
	})
}
func (m *semanticModel) checkFamilySelection(c *semanticCollector) {
	solver := m.selectionSolver()
	if len(solver.groups) == 0 {
		return
	}
	valid, exhausted := solver.witness(-1)
	if exhausted {
		c.report(semanticOwner{}, "Variation point constraints exceed the deterministic satisfiability budget")
		return
	}
	if !valid {
		c.report(semanticOwner{}, "Variation point constraints have no satisfying selection")
		return
	}
	for _, group := range solver.groups {
		for _, id := range group.members {
			valid, exhausted = solver.witness(id)
			if exhausted {
				c.report(semanticOwner{}, "Variation point constraints exceed the deterministic satisfiability budget")
				return
			}
			if !valid {
				variable := solver.variables[id]
				c.report(semanticOwner{variationPointsField, variable.point}, fmt.Sprintf("Variation point '%s' member '%s' cannot participate in any satisfying selection", variable.point, variable.member))
			}
		}
	}
}

type semanticSelectionState struct {
	solver *semanticSelectionSolver
	values []byte
	trail  []int
	seen   map[string]bool
}

func (s *semanticSelectionSolver) witness(required int) (bool, bool) {
	state := semanticSelectionState{solver: s, values: make([]byte, len(s.variables)), seen: map[string]bool{}}
	if required >= 0 {
		state.values[required] = selectionTrue
	}
	return state.search()
}
func (s *semanticSelectionState) assign(variable int, value byte) bool {
	if s.values[variable] != selectionUnknown {
		return s.values[variable] == value
	}
	s.values[variable] = value
	s.trail = append(s.trail, variable)
	return true
}
func (s *semanticSelectionState) undo(checkpoint int) {
	for _, variable := range s.trail[checkpoint:] {
		s.values[variable] = selectionUnknown
	}
	s.trail = s.trail[:checkpoint]
}
func (s *semanticSelectionState) key() string {
	encoded := make([]byte, (len(s.values)+3)/4)
	for i, value := range s.values {
		encoded[i/4] |= value << uint(2*(i%4))
	}
	return string(encoded)
}
func (s *semanticSelectionState) search() (bool, bool) {
	s.solver.remaining--
	if s.solver.remaining < 0 {
		return false, true
	}
	checkpoint := len(s.trail)
	if !s.propagate() {
		s.undo(checkpoint)
		return false, false
	}
	key := s.key()
	if s.seen[key] {
		s.undo(checkpoint)
		return false, false
	}
	s.seen[key] = true
	variable := -1
	for _, id := range s.solver.branch {
		if s.values[id] == selectionUnknown {
			variable = id
			break
		}
	}
	if variable < 0 {
		return true, false
	}
	for _, value := range []byte{selectionTrue, selectionFalse} {
		branch := len(s.trail)
		if s.assign(variable, value) {
			valid, exhausted := s.search()
			if valid || exhausted {
				return valid, exhausted
			}
		}
		s.undo(branch)
	}
	s.undo(checkpoint)
	return false, false
}
