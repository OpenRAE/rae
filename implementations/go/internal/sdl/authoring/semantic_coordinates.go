package authoring

import "encoding/json"

type semanticCoordinate struct {
	Tick      json.Number `json:"tick"`
	Microstep json.Number `json:"microstep"`
}
type semanticInterval struct{ start, end *semanticCoordinate }

func decodeSemanticCoordinate(raw json.RawMessage) (*semanticCoordinate, error) {
	var coordinate *semanticCoordinate
	if len(raw) == 0 {
		raw = json.RawMessage(nullType)
	}
	if err := json.Unmarshal(raw, &coordinate); err != nil {
		return nil, invalid()
	}
	if coordinate != nil {
		if coordinate.Tick == "" {
			coordinate.Tick = "0"
		}
		if coordinate.Microstep == "" {
			coordinate.Microstep = "0"
		}
	}
	return coordinate, nil
}
func (coordinate semanticCoordinate) before(other semanticCoordinate) bool {
	if modelLess(coordinate.Tick, other.Tick) {
		return true
	}
	if modelLess(other.Tick, coordinate.Tick) {
		return false
	}
	return modelLess(coordinate.Microstep, other.Microstep)
}
