package authoring

func (s *semanticSelectionState) propagate() bool {
	for {
		consistent, changed := s.clauses()
		if !consistent {
			return false
		}
		groupsConsistent, groupsChanged := s.groups()
		if !groupsConsistent {
			return false
		}
		if !changed && !groupsChanged {
			return true
		}
	}
}
func (s *semanticSelectionState) clauses() (bool, bool) {
	changed := false
	for _, clause := range s.solver.clauses {
		consistent, step := s.clause(clause)
		if !consistent {
			return false, changed
		}
		changed = changed || step
	}
	return true, changed
}
func (s *semanticSelectionState) clause(clause [2]semanticSelectionLiteral) (bool, bool) {
	unknown := 0
	var unit semanticSelectionLiteral
	for _, literal := range clause {
		value := s.values[literal.variable]
		if value == literal.value {
			return true, false
		}
		if value == selectionUnknown {
			unknown++
			unit = literal
		}
	}
	if unknown == 0 {
		return false, false
	}
	if unknown == 1 {
		consistent := s.assign(unit.variable, unit.value)
		return consistent, consistent
	}
	return true, false
}
func (s *semanticSelectionState) groups() (bool, bool) {
	changed := false
	for _, group := range s.solver.groups {
		consistent, step := s.group(group)
		if !consistent {
			return false, changed
		}
		changed = changed || step
	}
	return true, changed
}
func (s *semanticSelectionState) group(group semanticSelectionGroup) (bool, bool) {
	selected, unknown := 0, 0
	for _, id := range group.members {
		if s.values[id] == selectionTrue {
			selected++
		}
		if s.values[id] == selectionUnknown {
			unknown++
		}
	}
	if selected > group.maximum || selected+unknown < group.minimum {
		return false, false
	}
	forced := selectionUnknown
	if selected == group.maximum {
		forced = selectionFalse
	} else if selected+unknown == group.minimum {
		forced = selectionTrue
	}
	if forced == selectionUnknown {
		return true, false
	}
	return s.force(group.members, forced)
}

func (s *semanticSelectionState) force(members []int, forced byte) (bool, bool) {
	changed := false
	for _, id := range members {
		if s.values[id] == selectionUnknown {
			if !s.assign(id, forced) {
				return false, changed
			}
			changed = true
		}
	}
	return true, changed
}
