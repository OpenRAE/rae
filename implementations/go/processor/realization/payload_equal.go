package realization

import (
	"encoding/json"
	"math/big"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

// Residual payload matching keeps the reference's native JSON equality.
// Constraint relations retain their separate strict scalar grammar.
func payloadEqual(left, right any) bool { return projectionEqual(left, right, false) }
func projectionEqual(left, right any, strict bool) bool {
	switch first := left.(type) {
	case nil:
		return right == nil
	case map[string]any:
		return projectionMapEqual(first, right, strict)
	case []any:
		return projectionSliceEqual(first, right, strict)
	case string:
		second, ok := right.(string)
		return ok && first == second
	default:
		if strict {
			return domain.Equal(left, right)
		}
		firstNumber, firstOK := payloadNumber(left)
		secondNumber, secondOK := payloadNumber(right)
		return firstOK && secondOK && firstNumber.Cmp(secondNumber) == 0
	}
}
func projectionMapEqual(first map[string]any, input any, strict bool) bool {
	second, ok := input.(map[string]any)
	if !ok || len(first) != len(second) {
		return false
	}
	for key, value := range first {
		other, present := second[key]
		if !present || !projectionEqual(value, other, strict) {
			return false
		}
	}
	return true
}
func projectionSliceEqual(first []any, input any, strict bool) bool {
	second, ok := input.([]any)
	if !ok || len(first) != len(second) {
		return false
	}
	for i, value := range first {
		if !projectionEqual(value, second[i], strict) {
			return false
		}
	}
	return true
}

func payloadNumber(value any) (*big.Rat, bool) {
	switch number := value.(type) {
	case bool:
		if number {
			return big.NewRat(1, 1), true
		}
		return new(big.Rat), true
	case json.Number:
		if !strings.ContainsAny(string(number), ".eE") {
			integer, valid := new(big.Int).SetString(string(number), 10)
			if !valid {
				return nil, false
			}
			return new(big.Rat).SetInt(integer), true
		}
		parsed, err := strconv.ParseFloat(string(number), 64)
		if err != nil {
			return nil, false
		}
		rational := new(big.Rat).SetFloat64(parsed)
		return rational, rational != nil
	default:
		return nil, false
	}
}
