package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) apparatusManifests(i validation.Invocation) error {
	c, ok := i.Context.(ApparatusManifestContext)
	if !ok {
		return contextRequired()
	}
	processor, err := e.contextDocument(termProcessorManifestV2, c.ProcessorManifest())
	if err != nil {
		return err
	}
	backend, err := e.contextDocument(termBackendManifestV2, c.BackendManifest())
	if err != nil {
		return err
	}
	if err := manifestComponent(at(i.Instance, termComponents, kindProcessor), processor, kindProcessor+manifestV2Suffix, c.ProcessorManifestDigest()); err != nil {
		return err
	}
	if err := manifestComponent(at(i.Instance, termComponents, kindBackend), backend, kindBackend+manifestV2Suffix, c.BackendManifestDigest()); err != nil {
		return err
	}
	return require(set(at(processor, "compatibility", "backends"))[stringAt(backend, termIdentity, termName)] && set(at(backend, "compatibility", "processors"))[stringAt(processor, termIdentity, termName)])
}
func manifestComponent(component, manifest any, version, payloadDigest string) error {
	ref := at(component, "manifest_ref")
	if ref == nil || stringAt(ref, fieldRefID) != stringAt(manifest, termIdentity, termName) || stringAt(ref, fieldRefVersion) != version || !matchingFields(at(component, termIdentity), at(manifest, termIdentity), termName, "version") || at(ref, "subject_ref") == nil || !identityMatches(at(manifest, termIdentity), at(ref, "subject_ref")) {
		return invalid()
	}
	return require(at(ref, "ref_digest") == nil || payloadDigest != "" && strings.EqualFold(stringAt(ref, "ref_digest"), payloadDigest))
}
