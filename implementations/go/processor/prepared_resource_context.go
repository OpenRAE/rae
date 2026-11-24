package processor

import (
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type preparedContext struct {
	value       map[string]any
	environment map[string][]generatedNodeConsumer
	content     map[string][]generatedContentConsumer
}

const termMount = "mount"

// PreparedResourceContext reconstructs native resource specifications and
// checks every compiled grant before removing compiler projection fields.
func PreparedResourceContext(input admission.Fragment) (admission.Fragment, error) { //nolint:ireturn // The reviewed boundary returns an opaque native value handle.
	if err := admission.CheckFragment(input, admission.RealizationValue); err != nil {
		return nil, err
	}
	frame, ok := input.Document().(map[string]any)
	if !ok || len(frame) != 3 || preparedContextRecord(frame[termNodes]) == nil || preparedContextRecord(frame["infrastructure"]) == nil || preparedContextRecord(frame["resources"]) == nil {
		return nil, invalidCompiled()
	}
	context := preparedContext{value: map[string]any{"name": "prepared-node-context", termNodes: frame[termNodes], "infrastructure": frame["infrastructure"], termGeneratedArtifacts: map[string]any{}, termPersistentVolumes: map[string]any{}, termAccounts: map[string]any{}, termContent: map[string]any{}}, environment: map[string][]generatedNodeConsumer{}, content: map[string][]generatedContentConsumer{}}
	for compiledAddress, entry := range preparedContextRecord(frame["resources"]) {
		if err := context.resource(compiledAddress, entry); err != nil {
			return nil, err
		}
	}
	owner, err := processorAdmissionOwner()
	if err != nil {
		return nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, context.value, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return nil, err
	}
	derived, err := GeneratedArtifactConsumers(fragment)
	if err != nil {
		return nil, err
	}
	if !context.grantsMatch(derived) {
		return nil, invalidCompiled()
	}
	return fragment, nil
}

func preparedContextRecord(input any) map[string]any {
	record, _ := input.(map[string]any)
	return record
}
func preparedContextText(input any) string {
	text, _ := input.(string)
	return text
}

func (c *preparedContext) resource(compiledAddress string, input any) error {
	entry := preparedContextRecord(input)
	if len(entry) != 2 || entry["resource_type"] == nil || preparedContextRecord(entry["payload"]) == nil {
		return invalidCompiled()
	}
	kind := preparedContextText(entry["resource_type"])
	section := map[string]string{termGeneratedArtifact: termGeneratedArtifacts, termPersistentVolume: termPersistentVolumes, termAccountPlacement: termAccounts, termContentPlacement: termContent}[kind]
	if section == "" {
		return nil
	}
	payload := preparedContextRecord(entry["payload"])
	name := preparedContextText(payload["name"])
	spec := preparedContextRecord(payload["spec"])
	canonicalKind := map[string]string{termAccountPlacement: "account", termContentPlacement: termContent}[kind]
	if canonicalKind == "" {
		canonicalKind = kind
	}
	canonical, err := address.Render(termProvision, canonicalKind, name)
	if err != nil || canonical != compiledAddress || spec == nil {
		return invalidCompiled()
	}
	native := maps.Clone(spec)
	if kind == termGeneratedArtifact || kind == termPersistentVolume {
		consumers, err := preparedMountConsumers(spec["consumers"])
		if err != nil {
			return err
		}
		native["consumers"] = consumers
	}
	if kind == termGeneratedArtifact {
		if err := c.artifact(name, spec); err != nil {
			return err
		}
		delete(native, "environment_consumers")
		delete(native, "content_consumers")
	}
	preparedContextRecord(c.value[section])[name] = native
	return nil
}

func preparedMountConsumers(input any) ([]any, error) {
	if input == nil {
		return []any{}, nil
	}
	rows, ok := input.([]any)
	if !ok {
		return nil, invalidCompiled()
	}
	result := make([]any, 0, len(rows))
	for _, row := range rows {
		consumer := preparedContextRecord(row)
		if consumer == nil {
			return nil, invalidCompiled()
		}
		if mode, present := consumer["delivery_mode"]; present && mode != termMount {
			return nil, invalidCompiled()
		}
		canonical, err := address.Render(termProvision, termNode, preparedContextText(consumer[termNode]))
		if err != nil {
			return nil, err
		}
		if target, present := consumer["target_address"]; present && target != canonical {
			return nil, invalidCompiled()
		}
		native := maps.Clone(consumer)
		delete(native, "delivery_mode")
		delete(native, "target_address")
		result = append(result, native)
	}
	return result, nil
}

func (c *preparedContext) artifact(name string, spec map[string]any) error {
	environment, err := preparedProjectionRows(spec["environment_consumers"])
	if err != nil {
		return err
	}
	content, err := preparedProjectionRows(spec["content_consumers"])
	if err != nil {
		return err
	}
	if len(environment)+len(content)+len(preparedContextRows(spec["consumers"])) == 0 {
		return invalidCompiled()
	}
	for _, row := range environment {
		var consumer generatedNodeConsumer
		if json.Unmarshal(rawJSON(row), &consumer) != nil || !preparedEnvironmentGrant(row, consumer) {
			return invalidCompiled()
		}
		c.environment[name] = append(c.environment[name], consumer)
	}
	for _, row := range content {
		var consumer generatedContentConsumer
		if json.Unmarshal(rawJSON(row), &consumer) != nil || !preparedContentGrant(row, consumer) {
			return invalidCompiled()
		}
		c.content[name] = append(c.content[name], consumer)
	}
	return nil
}

func preparedContextRows(input any) []any {
	rows, _ := input.([]any)
	return rows
}

func preparedProjectionRows(input any) ([]any, error) {
	if input == nil {
		return []any{}, nil
	}
	rows, ok := input.([]any)
	if !ok {
		return nil, invalidCompiled()
	}
	return rows, nil
}

func preparedEnvironmentGrant(row any, consumer generatedNodeConsumer) bool {
	canonical, err := address.Render(termProvision, termNode, consumer.Node)
	if err != nil || canonical != consumer.TargetAddress || consumer.Output == "" || len(preparedContextRecord(row)) != 5 {
		return false
	}
	switch consumer.DeliveryMode {
	case "environment":
		return consumer.EnvironmentVariable != "" && consumer.EnvironmentFile == ""
	case "env_file":
		return consumer.EnvironmentFile != "" && consumer.EnvironmentVariable == ""
	default:
		return false
	}
}

func preparedContentGrant(row any, consumer generatedContentConsumer) bool {
	canonical, err := address.Render(termProvision, termContent, consumer.Content)
	return err == nil && canonical == consumer.TargetAddress && consumer.Output != "" && consumer.DeliveryMode == "content_text" && len(preparedContextRecord(row)) == 4
}

func (c *preparedContext) grantsMatch(derived map[string][]ArtifactConsumer) bool {
	environment := map[string]map[generatedNodeConsumer]bool{}
	content := map[string]map[generatedContentConsumer]bool{}
	for name, consumers := range derived {
		environment[name] = map[generatedNodeConsumer]bool{}
		content[name] = map[generatedContentConsumer]bool{}
		for _, consumer := range consumers {
			environment[name][generatedNodeConsumer{Node: consumer.Node, TargetAddress: consumer.TargetAddress, DeliveryMode: consumer.DeliveryMode, Output: consumer.Output, EnvironmentVariable: consumer.EnvironmentVariable, EnvironmentFile: consumer.EnvironmentFile}] = true
			content[name][generatedContentConsumer{Content: consumer.Content, TargetAddress: consumer.TargetAddress, DeliveryMode: consumer.DeliveryMode, Output: consumer.Output}] = true
		}
	}
	for name, grants := range c.environment {
		for _, grant := range grants {
			if !environment[name][grant] {
				return false
			}
		}
	}
	for name, grants := range c.content {
		for _, grant := range grants {
			if !content[name][grant] {
				return false
			}
		}
	}
	return true
}
