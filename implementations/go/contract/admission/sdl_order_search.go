package admission

import "crypto/sha256"

type sdlOrderSearch struct {
	predecessors [][]int
	fixed        map[int]int
	byPosition   map[int]int
	placed       []byte
	failed       map[[32]byte]bool
	states       int
}

type sdlOrderFrame struct {
	key      [32]byte
	selected int
	next     int
}

func newSDLOrderSearch(names []string, edges map[string][]string, fixed map[string]int) *sdlOrderSearch {
	search := &sdlOrderSearch{predecessors: make([][]int, len(names)), fixed: map[int]int{}, byPosition: map[int]int{}, placed: make([]byte, (len(names)+7)/8), failed: map[[32]byte]bool{}}
	indices := map[string]int{}
	for index, name := range names {
		indices[name] = index
	}
	for index, name := range names {
		for _, predecessor := range edges[name] {
			search.predecessors[index] = append(search.predecessors[index], indices[predecessor])
		}
	}
	for name, position := range fixed {
		index := indices[name]
		search.fixed[index], search.byPosition[position] = position, index
	}
	return search
}

func (s *sdlOrderSearch) isPlaced(index int) bool {
	return s.placed[index/8]&(1<<uint(index%8)) != 0
}

func (s *sdlOrderSearch) eligible(index, position int) bool {
	if s.isPlaced(index) {
		return false
	}
	if pinned, ok := s.fixed[index]; ok && pinned != position {
		return false
	}
	for _, predecessor := range s.predecessors[index] {
		if !s.isPlaced(predecessor) {
			return false
		}
	}
	return true
}

func (s *sdlOrderSearch) overdue(position int) bool {
	for index, pinned := range s.fixed {
		if pinned < position && !s.isPlaced(index) {
			return true
		}
	}
	return false
}

func (s *sdlOrderSearch) candidate(frame *sdlOrderFrame, position int) (int, bool) {
	if forced, ok := s.byPosition[position]; ok {
		if frame.next != 0 {
			return 0, false
		}
		frame.next = 1
		return forced, s.eligible(forced, position)
	}
	for frame.next < len(s.predecessors) {
		index := frame.next
		frame.next++
		if s.eligible(index, position) {
			return index, true
		}
	}
	return 0, false
}

func (s *sdlOrderSearch) hasWitness() bool {
	stack := []sdlOrderFrame{{key: sha256.Sum256(s.placed), selected: -1}}
	s.states = 1
	for len(stack) > 0 {
		position := len(stack) - 1
		if position == len(s.predecessors) {
			return true
		}
		frame := &stack[position]
		index, found := s.candidate(frame, position)
		if s.overdue(position) || !found {
			s.failed[frame.key] = true
			if frame.selected >= 0 {
				s.placed[frame.selected/8] &^= 1 << uint(frame.selected%8)
			}
			stack = stack[:position]
			continue
		}
		s.placed[index/8] |= 1 << uint(index%8)
		key := sha256.Sum256(s.placed)
		if s.failed[key] {
			s.placed[index/8] &^= 1 << uint(index%8)
			continue
		}
		s.states++
		if s.states > 100000 {
			return false
		}
		stack = append(stack, sdlOrderFrame{key: key, selected: index})
	}
	return false
}
