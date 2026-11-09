package sdlrules

import (
	"encoding/json"
	"math/big"
)

func coordinateInteger(value json.Number) (*big.Int, bool) {
	number, ok := new(big.Rat).SetString(string(value))
	if !ok || !number.IsInt() {
		return nil, false
	}
	return number.Num(), true
}
func (interval temporalInterval) invalid() bool {
	if interval.start == nil || interval.end == nil {
		return false
	}
	start, hasStart := coordinateInteger(interval.start.Tick)
	end, hasEnd := coordinateInteger(interval.end.Tick)
	if !hasStart || !hasEnd {
		return true
	}
	order := start.Cmp(end)
	if order != 0 {
		return order > 0
	}
	start, hasStart = coordinateInteger(interval.start.Microstep)
	end, hasEnd = coordinateInteger(interval.end.Microstep)
	return !hasStart || !hasEnd || start.Cmp(end) >= 0
}
