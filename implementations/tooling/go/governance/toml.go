package governance

import (
	"bytes"
	"strings"

	"github.com/pelletier/go-toml/v2"
	"github.com/pelletier/go-toml/v2/unstable"
)

func positioningTOMLDescription(source []byte) (string, bool) {
	masked, valid := positioningTOMLNumbers(source)
	if !valid {
		return "", false
	}
	var metadata map[string]any
	if err := toml.Unmarshal(masked, &metadata); err != nil {
		return "", false
	}
	project, _ := metadata["project"].(map[string]any)
	description, valid := project["description"].(string)
	return description, valid
}

// Only string metadata is consumed. After syntax admission, preserve numeric
// types but replace their values so the full decoder can validate all other
// values without imposing int64 or finite-float limits absent in the reference.
// Strings, keys and temporal values are never rewritten.
func positioningTOMLNumbers(source []byte) ([]byte, bool) {
	masked := bytes.Clone(source)
	var parser unstable.Parser
	parser.Reset(source)
	for parser.NextExpression() {
		if !positioningTOMLExpression(masked, parser.Expression()) {
			return nil, false
		}
	}
	return masked, parser.Error() == nil
}

func positioningTOMLExpression(masked []byte, expression *unstable.Node) bool {
	pending := []*unstable.Node{expression}
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		replacement, valid := positioningTOMLNumber(node)
		if !valid {
			return false
		}
		if replacement != "" {
			token := masked[node.Raw.Offset : node.Raw.Offset+node.Raw.Length]
			if len(token) < len(replacement) {
				return false
			}
			for i := range token {
				token[i] = ' '
			}
			copy(token, replacement)
		}
		for child := node.Child(); child != nil; child = child.Next() {
			pending = append(pending, child)
		}
	}
	return true
}

func positioningTOMLNumber(node *unstable.Node) (string, bool) {
	if node.Kind == unstable.Integer {
		return "0", tomlIntegerWithinLimit(string(node.Data))
	}
	if node.Kind == unstable.Float {
		return "0.0", true
	}
	return "", true
}

func tomlIntegerWithinLimit(raw string) bool {
	raw = strings.TrimLeft(raw, "+-")
	if strings.HasPrefix(raw, "0x") || strings.HasPrefix(raw, "0o") || strings.HasPrefix(raw, "0b") {
		return true
	}
	return len(strings.ReplaceAll(raw, "_", "")) <= 4300
}
