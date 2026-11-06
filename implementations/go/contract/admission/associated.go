package admission

import (
	"encoding/hex"
	"io"
	"maps"
	"reflect"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

// AssociatedArtifactsContext binds admitted parent identity and explicit byte
// readers. Readers remain caller-owned; admission never resolves a locator.
type AssociatedArtifactsContext interface {
	AssociatedParent() validation.Value
	AssociatedParentDigest() string
	AssociatedPayloads() map[string]io.Reader
}

func (e *Validator) associatedRules() map[string]definition {
	return map[string]definition{"associated-artifact-parent-set-and-byte-binding": {check: e.associatedArtifacts, contextual: true, requiresContext: true}}
}

func (e *Validator) associatedArtifacts(i validation.Invocation) error {
	context, ok := i.Context.(AssociatedArtifactsContext)
	if !ok {
		return contextRequired()
	}
	v, err := e.defaulted(termAssociatedArtifactManifestV1, i.Instance)
	if err != nil {
		return err
	}
	associatedSatisfactionDefaults(v)
	if err = associatedLocal(v); err != nil {
		return err
	}
	if err = associatedParent(v, context.AssociatedParent(), context.AssociatedParentDigest()); err != nil {
		return err
	}
	digest, err := associatedSetDigest(v)
	if err != nil || digest != stringAt(v, "set_digest") {
		return invalid()
	}
	return associatedBytes(at(v, "artifacts"), context.AssociatedPayloads())
}

// associatedSetDigest derives the published abstract set identity of a manifest
// whose omitted satisfaction references are already empty lists.
func associatedSetDigest(v any) (string, error) {
	projection := map[string]any{termProfile: at(v, "canonicalization_profile"), "scope": at(v, "scope"), "parent_ref": at(v, "parent_ref"), "artifacts": at(v, "artifacts")}
	associatedNormalize(projection)
	return jsonDigest(projection)
}

// associatedSatisfactionDefaults applies the model's empty-list default.
func associatedSatisfactionDefaults(v any) {
	for _, artifact := range object(at(v, "artifacts")) {
		if at(artifact, "satisfies_refs") == nil {
			object(artifact)["satisfies_refs"] = []any{}
		}
	}
}

func associatedParent(manifest any, parent validation.Value, digest string) error {
	shape := map[string][]string{
		kindScenario:                   {termSdlAuthoringInputV1, termName, "version"},
		kindScenarioSnapshot:           {termSdlAuthoringInputV1, termName, "version"},
		kindMaterializationAttestation: {termMaterializedScenarioV1, "materialization_provenance", ""},
		"task":                         {termExperimentTaskV1, "task_id", "task_version"},
		termAuthoringInput:             {termExperimentAuthoringInputV1, "spec_id", "spec_version"},
		"apparatus-context":            {"experiment-apparatus-context-v1", "apparatus_context_id", "context_version"},
		kindRun:                        {termExperimentRunV1, termRunID, "run_version"},
		"study":                        {"experiment-study-v1", "study_id", "study_version"},
	}
	ref := at(manifest, "parent_ref")
	kind := stringAt(ref, "ref_kind")
	fields := shape[kind]
	if len(fields) != 3 || parent.ContractID() != fields[0] {
		return invalid()
	}
	v, err := ingress.Parse(parent.JSON(), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return err
	}
	if kind == kindMaterializationAttestation {
		return require(equal(at(v, "materialization_provenance", "attestation_id"), at(ref, "ref_id")) && stringAt(ref, "ref_version") == termRaesSdlMaterializedV1 && stringAt(ref, "ref_digest") == digest && digest != "")
	}
	if !equal(at(v, fields[1]), at(ref, "ref_id")) {
		return invalid()
	}
	if kind == kindScenario {
		return nil
	}
	if at(ref, "ref_version") != nil && !equal(at(v, fields[2]), at(ref, "ref_version")) {
		return invalid()
	}
	return require(kind != kindScenarioSnapshot || at(ref, "ref_digest") == nil || digest != "" && strings.EqualFold(digest, stringAt(ref, "ref_digest")))
}

// associatedNormalize implements exclude_none and the two case-folded fields
// of the published abstract set identity. It only touches a fresh default view.
func associatedNormalize(v any) {
	switch node := v.(type) {
	case []any:
		for _, child := range node {
			associatedNormalize(child)
		}
	case map[string]any:
		for key, child := range node {
			if child == nil {
				delete(node, key)
				continue
			}
			associatedNormalize(child)
			if key == "ref_digest" {
				node[key] = strings.ToLower(text(child))
			}
		}
		if checksum := object(node["checksum"]); checksum != nil {
			checksum["value"] = strings.ToLower(text(checksum["value"]))
		}
	}
}

func associatedBytes(artifacts any, readers map[string]io.Reader) error {
	if len(object(artifacts)) > 1024 || len(object(artifacts)) != len(readers) {
		return invalid()
	}
	var total int64
	for id, artifact := range object(artifacts) {
		size, ok := integer(at(artifact, "size_bytes"))
		if !ok || size < 0 || size > 1073741824 || readers[id] == nil {
			return invalid()
		}
		total += int64(size)
		if total > 4294967296 {
			return invalid()
		}
	}
	for id, artifact := range object(artifacts) {
		size, _ := integer(at(artifact, "size_bytes"))
		if err := associatedPayload(artifact, readers[id], int64(size)); err != nil {
			return err
		}
	}
	return nil
}

func associatedPayload(artifact any, reader io.Reader, size int64) error {
	if associatedReaderMissing(reader) {
		return invalid()
	}
	checksum, ok := digest.NewChecksum(stringAt(artifact, "checksum", "algorithm"))
	if !ok {
		return invalid()
	}
	actual, err := io.CopyBuffer(checksum, io.LimitReader(reader, size+1), make([]byte, 64*1024))
	return require(err == nil && actual == size && strings.EqualFold(hex.EncodeToString(checksum.Sum(nil)), stringAt(artifact, "checksum", "value")))
}

func associatedReaderMissing(reader io.Reader) bool {
	if reader == nil {
		return true
	}
	v := reflect.ValueOf(reader)
	kind := v.Kind()
	return (kind == reflect.Chan || kind == reflect.Func || kind == reflect.Interface || kind == reflect.Map || kind == reflect.Pointer || kind == reflect.Slice) && v.IsNil()
}

func associatedLocal(v any) error {
	if err := associatedParentReference(at(v, "parent_ref")); err != nil {
		return err
	}
	if !keyed(at(v, "artifacts"), termArtifactID) {
		return invalid()
	}
	scenario := map[string]bool{kindScenario: true, kindScenarioSnapshot: true, kindMaterializationAttestation: true}[stringAt(v, "parent_ref", "ref_kind")]
	if (stringAt(v, "scope") == kindScenario) != scenario {
		return invalid()
	}
	descriptors, locators := map[string]bool{}, map[string]string{}
	for _, artifact := range object(at(v, "artifacts")) {
		if err := associatedDescriptor(artifact, descriptors, locators); err != nil {
			return err
		}
	}
	return nil
}

func associatedParentReference(v any) error {
	switch stringAt(v, "ref_kind") {
	case kindScenario:
		return require(at(v, "ref_version") == nil && at(v, "ref_digest") == nil && at(v, "ref_path") == nil)
	case kindMaterializationAttestation:
		return require(stringAt(v, "ref_version") == termRaesSdlMaterializedV1 && at(v, "ref_digest") != nil && at(v, "ref_path") != nil)
	case kindScenarioSnapshot:
		return nil
	default:
		return require(at(v, "ref_digest") == nil && at(v, "ref_path") == nil)
	}
}

func associatedDescriptor(artifact any, descriptors map[string]bool, locators map[string]string) error {
	if err := urisafety.Check(stringAt(artifact, "uri"), urisafety.Options{}); err != nil {
		return invalid()
	}
	descriptor := maps.Clone(object(artifact))
	if descriptor["satisfies_refs"] == nil {
		descriptor["satisfies_refs"] = []any{}
	}
	if _, ok := descriptor["description"]; !ok {
		descriptor["description"] = nil
	}
	delete(descriptor, termArtifactID)
	checksum := maps.Clone(object(at(artifact, "checksum")))
	checksum["value"] = strings.ToLower(text(checksum["value"]))
	descriptor["checksum"] = checksum
	key, err := jsonDigest(descriptor)
	if err != nil || descriptors[key] {
		return invalid()
	}
	descriptors[key] = true
	claim, err := jsonDigest([]any{at(artifact, "media_type"), checksum, at(artifact, "size_bytes")})
	if err != nil {
		return err
	}
	uri := stringAt(artifact, "uri")
	if previous, exists := locators[uri]; exists && previous != claim {
		return invalid()
	}
	locators[uri] = claim

	return nil
}
