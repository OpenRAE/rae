package admission

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"math"
	"math/big"
	"path"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

const experimentInputBytes = 64 * 1024

func experimentError(code string) error { return fault.New(fault.InvalidInput, code, nil) }

// ParseExperiment admits one bounded experiment document and an optional exact task.
// It rejects aliases and duplicate keys; it does not use SDL import semantics.
func ParseExperiment(data []byte, task *validation.Value) (validation.Value, error) {
	if len(data) > experimentInputBytes {
		return validation.Value{}, experimentError("input-too-large")
	}
	if len(bytes.TrimSpace(data)) == 0 {
		return validation.Value{}, experimentError("empty-input")
	}
	if !utf8.Valid(data) {
		return validation.Value{}, experimentError("invalid-yaml")
	}
	document, err := parseExperimentYAML(data)
	if err != nil {
		return validation.Value{}, err
	}
	owner, err := packagedAdmission()
	if err != nil {
		return validation.Value{}, err
	}
	if err = owner.coerceExperimentBinary(document); err != nil {
		return validation.Value{}, err
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return validation.Value{}, experimentError("contract-invalid")
	}
	raw, err = owner.experimentProjection(termExperimentAuthoringInputV1, raw)
	if err != nil {
		return validation.Value{}, experimentError("contract-invalid")
	}
	var canonical any
	if decodeExact(raw, &canonical) != nil {
		return validation.Value{}, experimentError("contract-invalid")
	}
	if task != nil && !experimentTaskMatches(canonical, *task) {
		return validation.Value{}, experimentError("task-reference-mismatch")
	}
	admitted, err := owner.low.Validate(termExperimentAuthoringInputV1, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		return validation.Value{}, experimentError("contract-invalid")
	}
	return admitted, nil
}

func experimentTaskMatches(document any, task validation.Value) bool {
	if task.ContractID() != "experiment-task-v1" {
		return false
	}
	var target any
	if decodeExact(task.JSON(), &target) != nil {
		return false
	}
	ref := at(document, "task_ref")
	return equal(at(ref, "ref_id"), at(target, "task_id")) && (at(ref, "ref_version") == nil || equal(at(ref, "ref_version"), at(target, "task_version")))
}

// LoadExperiment bounds the opened stream, even if its size changes after Stat.
func LoadExperiment(source fs.FS, path string, task *validation.Value) (validation.Value, error) {
	if source == nil || !fs.ValidPath(path) {
		return validation.Value{}, experimentError("experiment-source-invalid")
	}
	file, err := source.Open(path)
	if err != nil {
		return validation.Value{}, experimentReadError(err)
	}
	defer func() { _ = file.Close() }()
	info, err := file.Stat()
	if err != nil {
		return validation.Value{}, experimentReadError(err)
	}
	if info.Size() > experimentInputBytes {
		return validation.Value{}, experimentError("input-too-large")
	}
	raw, err := io.ReadAll(io.LimitReader(file, experimentInputBytes+1))
	if err != nil {
		return validation.Value{}, experimentReadError(err)
	}
	return ParseExperiment(raw, task)
}

func experimentReadError(err error) error {
	if errors.Is(err, fs.ErrNotExist) {
		return fault.New(fault.NotFound, "experiment-not-found", nil)
	}
	return fault.New(fault.Operational, "experiment-read-failed", nil)
}

// DiscoverExperiments returns sorted direct children with the authored suffix.
func DiscoverExperiments(source fs.FS, directory string) ([]string, error) {
	if source == nil || !fs.ValidPath(directory) {
		return nil, experimentError("experiment-source-invalid")
	}
	info, err := fs.Stat(source, directory)
	if errors.Is(err, fs.ErrNotExist) {
		return []string{}, nil
	}
	if err != nil {
		return nil, experimentReadError(err)
	}
	if !info.IsDir() {
		return []string{}, nil
	}
	entries, err := fs.ReadDir(source, directory)
	if err != nil {
		return nil, experimentReadError(err)
	}
	output := []string{}
	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), ".exp.yaml") {
			output = append(output, path.Join(directory, entry.Name()))
		}
	}
	slices.Sort(output)
	return output, nil
}

type experimentYAMLState struct{ invalidJSON, unsupported bool }

func parseExperimentYAML(data []byte) (map[string]any, error) {
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	var document yaml.Node
	if err := decoder.Decode(&document); err != nil {
		if errors.Is(err, io.EOF) {
			return nil, experimentError("invalid-root")
		}
		return nil, experimentError("invalid-yaml")
	}
	var extra yaml.Node
	if !errors.Is(decoder.Decode(&extra), io.EOF) {
		return nil, experimentError("invalid-yaml")
	}
	if len(document.Content) == 0 {
		return nil, experimentError("invalid-root")
	}
	if experimentHasAlias(&document) {
		return nil, experimentError("invalid-yaml")
	}
	state := experimentYAMLState{}
	value, err := state.node(document.Content[0], 0)
	if err != nil {
		return nil, err
	}
	root, ok := value.(map[string]any)
	if !ok {
		return nil, experimentError("invalid-root")
	}
	if state.invalidJSON {
		return nil, experimentError("invalid-json-value")
	}
	if state.unsupported {
		return nil, experimentError("contract-invalid")
	}
	return root, nil
}

func experimentHasAlias(node *yaml.Node) bool {
	stack := []*yaml.Node{node}
	for len(stack) > 0 {
		next := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if next.Kind == yaml.AliasNode {
			return true
		}
		stack = append(stack, next.Content...)
	}
	return false
}

func (s *experimentYAMLState) node(node *yaml.Node, depth int) (any, error) {
	if depth > 512 {
		return nil, experimentError("invalid-yaml")
	}
	switch node.Kind {
	case yaml.MappingNode:
		return s.mapping(node, depth)
	case yaml.SequenceNode:
		return s.sequence(node, depth)
	case yaml.ScalarNode:
		return s.scalar(node)
	case yaml.DocumentNode, yaml.AliasNode:
		return nil, experimentError("invalid-yaml")
	default:
		return nil, experimentError("invalid-yaml")
	}
}

func (s *experimentYAMLState) sequence(node *yaml.Node, depth int) (any, error) {
	if node.Tag != "!!seq" {
		s.unsupported = true
		return experimentUnsupported{}, nil
	}
	result := make([]any, 0, len(node.Content))
	for _, child := range node.Content {
		v, err := s.node(child, depth+1)
		if err != nil {
			return nil, err
		}
		result = append(result, v)
	}
	return result, nil
}
func (s *experimentYAMLState) scalar(node *yaml.Node) (any, error) {
	value, err := experimentScalar(node)
	if err != nil {
		return nil, err
	}
	if f, ok := value.(float64); ok && (math.IsNaN(f) || math.IsInf(f, 0)) {
		s.invalidJSON = true
	}
	if _, ok := value.(experimentUnsupported); ok {
		s.unsupported = true
	}
	return value, nil
}
func (s *experimentYAMLState) mapping(node *yaml.Node, depth int) (any, error) {
	if node.Tag != "!!map" {
		s.unsupported = true
		return experimentUnsupported{}, nil
	}
	keys := make([]any, 0, len(node.Content)/2)
	seen := map[string]bool{}
	for i := 0; i < len(node.Content); i += 2 {
		if node.Content[i].Kind != yaml.ScalarNode {
			return nil, experimentError("invalid-yaml")
		}
		key, err := s.node(node.Content[i], depth+1)
		if err != nil {
			return nil, err
		}
		identity := experimentKey(key, i)
		if seen[identity] {
			return nil, experimentError("duplicate-key")
		}
		seen[identity] = true
		keys = append(keys, key)
	}
	result := map[string]any{}
	for i, key := range keys {
		value, err := s.node(node.Content[2*i+1], depth+1)
		if err != nil {
			return nil, err
		}
		name, ok := key.(string)
		if !ok {
			s.invalidJSON = true
			continue
		}
		result[name] = value
	}
	return result, nil
}

func experimentKey(key any, position int) string {
	switch value := key.(type) {
	case string:
		return "s:" + value
	case nil:
		return termNull
	case bool:
		if value {
			return "n:1"
		}
		return "n:0"
	case json.Number:
		if n, ok := new(big.Rat).SetString(value.String()); ok {
			return "n:" + n.RatString()
		}
	case float64:
		if math.IsNaN(value) {
			return "nan:" + strconv.Itoa(position)
		}
		return "f:" + strconv.FormatFloat(value, 'g', -1, 64)
	case experimentBinary:
		return "b:" + base64.StdEncoding.EncodeToString(value.data)
	case experimentUnsupported:
		return "unsupported:" + value.key
	}
	return "invalid"
}
