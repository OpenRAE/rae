package admission

import (
	"math"
	"path"
	"slices"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) statefulRules() map[string]definition {
	return map[string]definition{
		"stateful-generated-artifact-semantics": {check: generatedArtifacts},
		"stateful-persistent-volume-semantics":  {check: persistentVolumes},
		"stateful-cross-resource-semantics":     {check: statefulReferences},
		"initial-service-state-semantics":       {check: serviceMaterialization},
	}
}
func sdlInstance(i validation.Invocation) any {
	v := invocationRoot(i)
	if at(v, kindScenario) != nil {
		return at(v, kindScenario)
	}
	return v
}
func containedPath(v string, absolute bool) bool {
	if v == "" || v == "." || v == "/" || strings.HasPrefix(v, "//") || strings.Contains(v, "\\") || strings.HasPrefix(v, "/") != absolute || path.Clean(v) != v {
		return false
	}
	if slices.Contains(strings.Split(v, "/"), "..") {
		return false
	}
	for _, r := range v {
		if r < 32 || r == 127 {
			return false
		}
	}
	return true
}
func generatedArtifacts(i validation.Invocation) error {
	for _, v := range object(at(sdlInstance(i), fieldGeneratedArtifacts)) {
		if err := generatedArtifact(v); err != nil {
			return err
		}
	}
	return nil
}
func generatedArtifact(v any) error {
	outputs, consumers := array(at(v, "outputs")), array(at(v, "consumers"))
	if len(rowSet(outputs, termName)) != len(outputs) || len(rowSet(outputs, "path")) != len(outputs) || len(rowTupleSet(consumers, termNode, "mount_destination")) != len(consumers) || !fieldsUnique(v, termOrderingDependencies, termRefreshDependencies) {
		return invalid()
	}
	for _, output := range outputs {
		if !containedPath(stringAt(output, "path"), false) {
			return invalid()
		}
	}
	selected, err := generatedSelections(v)
	if err != nil {
		return err
	}
	if err := sshSelectedOutputs(v, selected); err != nil {
		return err
	}
	if stringAt(v, "generator") != "random_value" {
		return require(at(v, "random_value") == nil && at(v, "regeneration_scope") == nil)
	}
	if at(v, "random_value") == nil || at(v, "regeneration_scope") == nil || len(outputs) != 1 {
		return invalid()
	}
	floor := countAt(v, "random_value", "min_entropy_bits")
	if stringAt(outputs[0], "sensitivity") == sensitivitySecret {
		floor = max(floor, 128)
	}
	return randomRecipe(at(v, "random_value"), floor)
}
func generatedSelections(v any) (map[string]bool, error) {
	selected := map[string]bool{}
	for _, consumer := range array(at(v, "consumers")) {
		if !containedPath(stringAt(consumer, "mount_destination"), true) || stringAt(consumer, "access_mode") != "read_only" || !fieldsUnique(consumer, "selected_outputs") {
			return nil, invalid()
		}
		if (object(at(v, "generator")) != nil || stringAt(v, "generator") == "ssh_key_bundle") && len(array(at(consumer, "selected_outputs"))) == 0 {
			return nil, invalid()
		}
		for _, name := range stringsOf(at(consumer, "selected_outputs")) {
			output := generatedOutput(v, name)
			if output == nil {
				return nil, invalid()
			}
			selected[name] = true
		}
	}
	return selected, nil
}
func generatedOutput(artifact any, name string) any {
	for _, output := range array(at(artifact, "outputs")) {
		if stringAt(output, termName) == name && stringAt(output, "disposition") != "producer_private" {
			return output
		}
	}
	return nil
}
func randomRecipe(v any, floor int) error {
	if (at(v, "alphabet") == nil) == (at(v, "custom_alphabet") == nil) || (at(v, "length") == nil) == (at(v, "entropy_bits") == nil) {
		return invalid()
	}
	size := map[string]int{"hex_lower": 16, "hex_upper": 16, "digits": 10, "alpha": 52, "alphanumeric": 62, "base32": 32, "base58": 58}[stringAt(v, "alphabet")]
	if at(v, "custom_alphabet") != nil {
		var err error
		size, err = randomAlphabetSize(stringAt(v, "custom_alphabet"))
		if err != nil {
			return err
		}
	}
	if size < 2 {
		return invalid()
	}
	bits := math.Log2(float64(size))
	length := countAt(v, "length")
	entropy := float64(length) * bits
	if at(v, "entropy_bits") != nil {
		entropy = float64(countAt(v, "entropy_bits"))
		length = int(math.Ceil(entropy / bits))
	}
	for _, field := range []string{"prefix", "suffix"} {
		for _, r := range stringAt(v, "format", field) {
			if r < 32 || r == 127 {
				return invalid()
			}
		}
	}
	rendered := length + utf8.RuneCountInString(stringAt(v, "format", "prefix")) + utf8.RuneCountInString(stringAt(v, "format", "suffix"))
	return require(rendered <= 4096 && entropy >= float64(floor))
}
func persistentVolumes(i validation.Invocation) error {
	for _, v := range object(at(sdlInstance(i), "persistent_volumes")) {
		if err := persistentVolume(v); err != nil {
			return err
		}
	}
	return nil
}

func sshSelectedOutputs(v any, selected map[string]bool) error {
	outputs := array(at(v, "outputs"))
	if stringAt(v, "generator") == "ssh_key_bundle" {
		for _, output := range outputs {
			if text(defaultMember(output, "disposition", "consumer_selected")) == "consumer_selected" && !selected[stringAt(output, termName)] {
				return invalid()
			}
		}
	}
	return nil
}

func randomAlphabetSize(alphabet string) (int, error) {
	seen := map[rune]bool{}
	for _, r := range alphabet {
		if r < 32 || r == 127 || unicode.IsSpace(r) || seen[r] {
			return 0, invalid()
		}
		seen[r] = true
	}
	return len(seen), nil
}

func persistentVolume(v any) error {
	consumers := array(at(v, "consumers"))
	if len(rowTupleSet(consumers, termNode, "mount_destination")) != len(consumers) || !fieldsUnique(v, termOrderingDependencies, termRefreshDependencies) {
		return invalid()
	}
	writers := map[string]bool{}
	for _, consumer := range consumers {
		if !containedPath(stringAt(consumer, "mount_destination"), true) {
			return invalid()
		}
		if stringAt(consumer, "access_mode") == "read_write" {
			writers[stringAt(consumer, termNode)] = true
		}
	}
	mode := stringAt(v, "access_mode")
	if mode == "read_only_many" && len(writers) > 0 || mode == "read_write_once" && len(writers) > 1 {
		return invalid()
	}

	return nil
}
