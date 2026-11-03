package validation

import (
	"bytes"
	"encoding/json"
	"io"
	"math/big"
	"net/url"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type inertNode struct {
	value   any
	keys    []string
	members map[string]*inertNode
	items   []*inertNode
	nodes   int
}
type inertReader struct {
	decoder            *json.Decoder
	limits             InertLimits
	nodes, scalarBytes int
}

func readInert(data []byte, limits InertLimits) (*inertNode, error) {
	if len(data) > limits.MaxBytes || !utf8.Valid(data) {
		return nil, inertFailure()
	}
	wrapped := append(append([]byte{'['}, data...), ']')
	if _, err := ingress.Parse(wrapped, ingress.Limits{MaxBytes: limits.MaxBytes + 2, MaxDepth: limits.MaxDepth + 2}, ingress.Array); err != nil {
		return nil, inertFailure()
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.UseNumber()
	r := inertReader{decoder: d, limits: limits}
	n, err := r.node(0)
	if err != nil {
		return nil, err
	}
	if _, err := d.Token(); err != io.EOF {
		return nil, inertFailure()
	}
	n.nodes = r.nodes
	return n, nil
}
func (r *inertReader) scalar(v any) bool {
	size := 1
	switch v := v.(type) {
	case string:
		size = len(v)
	case json.Number:
		if !boundedNumber(v) {
			return false
		}
		if strings.ContainsAny(v.String(), ".eE") {
			if _, err := strconv.ParseFloat(v.String(), 64); err != nil {
				return false
			}
		} else {
			n, ok := new(big.Int).SetString(v.String(), 10)
			if !ok {
				return false
			}
			size = max(1, (n.BitLen()+7)/8)
		}
	}
	r.scalarBytes += size
	return r.scalarBytes <= r.limits.MaxScalarBytes
}
func (r *inertReader) node(depth int) (*inertNode, error) {
	r.nodes++
	if r.nodes > r.limits.MaxNodes || depth > r.limits.MaxDepth {
		return nil, inertFailure()
	}
	token, err := r.decoder.Token()
	if err != nil {
		return nil, inertFailure()
	}
	n := &inertNode{value: token}
	switch token {
	case json.Delim('{'):
		return r.object(depth)
	case json.Delim('['):
		return r.array(depth)
	default:
		if !r.scalar(token) {
			return nil, inertFailure()
		}
	}
	return n, nil
}
func (r *inertReader) object(depth int) (*inertNode, error) {
	n := &inertNode{members: map[string]*inertNode{}}
	obj := map[string]any{}
	n.value = obj
	for r.decoder.More() {
		keyToken, err := r.decoder.Token()
		if err != nil {
			return nil, inertFailure()
		}
		key, ok := keyToken.(string)
		if !ok || n.members[key] != nil || !r.scalar(key) {
			return nil, inertFailure()
		}
		child, err := r.node(depth + 1)
		if err != nil {
			return nil, err
		}
		n.keys = append(n.keys, key)
		n.members[key] = child
		obj[key] = child.value
	}
	if end, err := r.decoder.Token(); err != nil || end != json.Delim('}') {
		return nil, inertFailure()
	}
	return n, nil
}
func (r *inertReader) array(depth int) (*inertNode, error) {
	n := &inertNode{}
	values := []any{}
	for r.decoder.More() {
		child, err := r.node(depth + 1)
		if err != nil {
			return nil, err
		}
		n.items = append(n.items, child)
		values = append(values, child.value)
	}
	if end, err := r.decoder.Token(); err != nil || end != json.Delim(']') {
		return nil, inertFailure()
	}
	n.value = values
	return n, nil
}
func inertPointer(root *inertNode, ref string) *inertNode {
	if !strings.HasPrefix(ref, "#/") {
		return nil
	}
	pointer, err := url.PathUnescape(ref[2:])
	if err != nil {
		return nil
	}
	for part := range strings.SplitSeq(pointer, "/") {
		part = strings.ReplaceAll(strings.ReplaceAll(part, "~1", "/"), "~0", "~")
		if root == nil {
			return nil
		}
		if root.members != nil {
			root = root.members[part]
		} else {
			index, err := strconv.Atoi(part)
			if err != nil || index < 0 || index >= len(root.items) {
				return nil
			}
			root = root.items[index]
		}
	}
	return root
}
func inertComparisonSize(v any) int {
	size := 1
	switch v := v.(type) {
	case map[string]any:
		size += len(v)
		for _, child := range v {
			size += inertComparisonSize(child)
		}
	case []any:
		for _, child := range v {
			size += inertComparisonSize(child)
		}
	}
	return size
}
func inertKeywordCost(keyword string, schema, value any) int {
	switch keyword {
	case keywordEnum:
		if candidates, ok := schema.([]any); ok {
			cost := len(candidates) * inertComparisonSize(value)
			for _, c := range candidates {
				cost += inertComparisonSize(c)
			}
			return max(1, cost)
		}
	case keywordConst:
		return inertComparisonSize(value) + inertComparisonSize(schema)
	}
	return 1
}
