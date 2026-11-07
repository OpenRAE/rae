package governance

import "math"

type publicationPair struct {
	left, right any
	child       bool
}

func publicationEqual(left, right any) bool {
	pending := []publicationPair{{left, right, false}}
	for len(pending) > 0 {
		pair := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		children, equal := publicationPairEqual(pair)
		if !equal {
			return false
		}
		pending = append(pending, children...)
	}
	return true
}

func publicationPairEqual(pair publicationPair) ([]publicationPair, bool) {
	switch left := pair.left.(type) {
	case *mapping:
		right := object(pair.right)
		if right == nil || left.size() != right.size() {
			return nil, false
		}
		children := make([]publicationPair, len(left.keys))
		for i, key := range left.keys {
			if !right.has(key) {
				return nil, false
			}
			children[i] = publicationPair{left.get(key), right.get(key), true}
		}
		return children, true
	case []any:
		right, ok := pair.right.([]any)
		if !ok || len(left) != len(right) {
			return nil, false
		}
		children := make([]publicationPair, len(left))
		for i := range left {
			children[i] = publicationPair{left[i], right[i], true}
		}
		return children, true
	default:
		return nil, publicationScalarEqual(pair)
	}
}

func publicationScalarEqual(pair publicationPair) bool {
	left, leftFloat := pair.left.(float64)
	right, rightFloat := pair.right.(float64)
	leftNaN, rightNaN := leftFloat && math.IsNaN(left), rightFloat && math.IsNaN(right)
	if leftNaN || rightNaN {
		// The reference decoder reuses its NaN singleton: Python container
		// equality recognizes that identity, while scalar NaN != NaN.
		return pair.child && leftNaN && rightNaN
	}
	// Existing YAML key normalization retains exact int/float equivalence,
	// including bool-as-int, without rounding a large integer to float64.
	return yamlKey(pair.left) == yamlKey(pair.right)
}
