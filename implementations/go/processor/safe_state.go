package processor

import "github.com/OpenRAE/rae/implementations/go/sdl"

// compileSafeStates retains the resolved safe-state proof for every phase plan.
func (state *compilerState) compileSafeStates() {
	if state.err != nil {
		return
	}
	state.model.SafeStates, state.err = sdl.SafeStates(state.input.scenario)
}
