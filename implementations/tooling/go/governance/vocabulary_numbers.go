package governance

import (
	"encoding/json"
	"math"
	"regexp"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// Source models accept integer strings, integral floats in the int64 range
// and booleans as positions. Keep that input profile before strict public contract admission.
func normalizeVocabularyPositions(id string, data []byte, ordered *mapping) ([]byte, error) {
	var field string
	switch id {
	case "atlas-tactics-source-v1":
		field = "tactics"
	case "w3c-activitystreams-activity-types-source-v1":
		field = "activity_types"
	case "fipa-communicative-acts-source-v1":
		field = "communicative_acts"
	default:
		return data, nil
	}
	// Parse the losslessly canonicalized bytes through the Unicode-strict
	// owner before encoding/json can replace any unpaired surrogate.
	value, err := ingress.Parse(data, ingress.Limits{MaxBytes: math.MaxInt, MaxDepth: 65000}, ingress.Object)
	if err != nil {
		return nil, err
	}
	root, _ := value.(map[string]any)
	rows, _ := root[field].([]any)
	original, _ := ordered.get(field).([]any)
	for i, row := range rows {
		item, ok := row.(map[string]any)
		if !ok || i >= len(original) || object(original[i]) == nil {
			continue // The public model owner reports malformed rows.
		}
		source := object(original[i])
		raw := source.get("position")
		position := vocabularyPosition(raw)
		if position == nil {
			if _, integer := raw.(json.Number); !integer {
				return nil, policyInputError("source position is not a supported integer representation")
			}
			continue
		}
		item["position"] = position
		source.set("position", position)
	}
	return json.Marshal(value)
}

func vocabularyPosition(value any) any {
	switch position := value.(type) {
	case bool:
		if position {
			return json.Number("1")
		}
		return json.Number("0")
	case float64:
		if position >= math.MinInt64 && position < math.MaxInt64 && math.Trunc(position) == position {
			if position == 0 {
				return json.Number("0")
			}
			return json.Number(strconv.FormatFloat(position, 'f', 0, 64))
		}
	case string:
		return vocabularyIntegerString(position)
	}
	return nil
}

func vocabularyIntegerString(text string) any {
	text = strings.TrimSpace(text)
	if !regexp.MustCompile(`^[+-]?(?:[0-9](?:_?[0-9])*|[0-9]+\.0+)$`).MatchString(text) {
		return nil
	}
	integer, _, _ := strings.Cut(strings.ReplaceAll(text, "_", ""), ".")
	sign := ""
	if strings.HasPrefix(integer, "-") {
		sign = "-"
	}
	digits := strings.TrimLeft(strings.TrimLeft(integer, "+-"), "0")
	if digits == "" {
		return json.Number("0")
	}
	if len(digits) > 4300 {
		return nil
	}
	return json.Number(sign + digits)
}
