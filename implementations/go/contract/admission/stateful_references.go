package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func resolveName(reference, section string, declarations any) (string, bool) {
	name := strings.TrimPrefix(reference, section+".")
	_, ok := object(declarations)[name]
	return name, ok
}
func statefulReferences(i validation.Invocation) error {
	v := sdlInstance(i)
	occupied := map[string]bool{}
	consumed := map[string]bool{}
	for _, section := range []string{fieldGeneratedArtifacts, "persistent_volumes"} {
		for name, resource := range object(at(v, section)) {
			if section == fieldGeneratedArtifacts && len(array(at(resource, "consumers"))) > 0 {
				consumed[name] = true
			}
			if err := resourceConsumers(v, resource, occupied); err != nil {
				return err
			}
			if err := resourceDependencies(v, resource); err != nil {
				return err
			}
		}
	}
	if err := generatedValueReferences(v, consumed); err != nil {
		return err
	}
	return statefulOrphansAndMounts(v, consumed, occupied)
}
func resourceConsumers(v, resource any, occupied map[string]bool) error {
	for _, consumer := range array(at(resource, "consumers")) {
		name, ok := resolveName(stringAt(consumer, termNode), "nodes", at(v, "nodes"))
		if !ok || stringAt(v, "nodes", name, "os") == termWindows {
			return invalid()
		}
		key := join(name, stringAt(consumer, "mount_destination"))
		if occupied[key] {
			return invalid()
		}
		occupied[key] = true
	}
	return nil
}
func resourceDependencies(v, resource any) error {
	for _, field := range []string{termOrderingDependencies, termRefreshDependencies} {
		for _, reference := range stringsOf(at(resource, field)) {
			count := resourceDependencyCount(v, reference)
			if count != 1 {
				return invalid()
			}
		}
	}
	return nil
}
func resolveGeneratedValue(v, source any, consumed map[string]bool) (any, error) {
	name, ok := resolveName(stringAt(source, "generated_artifact"), fieldGeneratedArtifacts, at(v, fieldGeneratedArtifacts))
	if !ok {
		return nil, invalid()
	}
	output := generatedOutput(at(v, fieldGeneratedArtifacts, name), stringAt(source, "output"))
	if output == nil {
		return nil, invalid()
	}
	consumed[name] = true
	return output, nil
}
func generatedValueReferences(v any, consumed map[string]bool) error {
	for _, node := range object(at(v, "nodes")) {
		if err := environmentGeneratedValues(v, node, consumed); err != nil {
			return err
		}
	}
	if err := contentGeneratedValues(v, consumed); err != nil {
		return err
	}
	for _, proposition := range object(at(v, "propositions")) {
		if source := at(proposition, "predicate", "expected_from"); source != nil {
			if stringAt(proposition, "basis") != "observed_state" {
				return invalid()
			}
			if _, err := resolveGeneratedValue(v, source, consumed); err != nil {
				return err
			}
		}
	}
	return nil
}
func environmentGeneratedValues(v, node any, consumed map[string]bool) error {
	for _, field := range []string{"environment", "environment_files"} {
		for _, entry := range array(at(node, "runtime", field)) {
			source := at(entry, "value_from")
			if source == nil {
				continue
			}
			output, err := resolveGeneratedValue(v, source, consumed)
			if err != nil {
				return err
			}
			classification := at(entry, "value_classification")
			if stringAt(output, "sensitivity") == sensitivitySecret && classification != nil && text(classification) != "redacted" {
				return invalid()
			}
		}
	}
	return nil
}

func statefulOrphansAndMounts(v any, consumed, occupied map[string]bool) error {
	for name, resource := range object(at(v, fieldGeneratedArtifacts)) {
		if len(array(at(resource, "consumers"))) == 0 && !consumed[name] {
			return invalid()
		}
	}
	for name, node := range object(at(v, "nodes")) {
		for _, mount := range array(at(node, "runtime", "mounts")) {
			if occupied[join(name, stringAt(mount, "target"))] {
				return invalid()
			}
		}
	}
	return nil
}

func contentGeneratedValues(v any, consumed map[string]bool) error {
	for _, content := range object(at(v, "content")) {
		if source := at(content, "text_from"); source != nil {
			output, err := resolveGeneratedValue(v, source, consumed)
			if err != nil {
				return err
			}
			if stringAt(output, "sensitivity") == sensitivitySecret && at(content, "sensitive") == false {
				return invalid()
			}
		}
	}
	return nil
}

func resourceDependencyCount(v any, reference string) int {
	count := 0
	for _, section := range []string{fieldGeneratedArtifacts, "persistent_volumes"} {
		name := reference
		if strings.HasPrefix(reference, "generated_artifacts.") || strings.HasPrefix(reference, "persistent_volumes.") {
			var ok bool
			name, ok = strings.CutPrefix(reference, section+".")
			if !ok {
				continue
			}
		}
		if _, ok := object(at(v, section))[name]; ok {
			count++
		}
	}
	return count
}
