package authoring

import (
	"encoding/json"
	"math/big"
)

func modelInteger(value any) (*big.Int, bool) {
	number, ok := value.(json.Number)
	if !ok {
		return nil, false
	}
	// Model ingress already bounds the coefficient/exponent and schema type.
	rational, ok := new(big.Rat).SetString(string(number))
	if !ok || !rational.IsInt() {
		return nil, false
	}
	return rational.Num(), true
}
