package profile

import (
	"bytes"
	"encoding/json"
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/contract/concept"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/packaged"
)

const (
	contractBackendProfile  = "backend-profile-v1"
	contractRelationProfile = "behavioral-relation-profile-v1"
	relationDir             = "profiles/behavioral-relation/"
	comparisonDir           = "profiles/semantic-comparison/"
	completenessDir         = "profiles/scientific-completeness/"
	pathValidation          = "profiles/validation/validation-profile-catalog-v1.json"
	pathTaxonomy            = completenessDir + "scientific-scenario-completeness-rev1.json"
)

// packagedFiles returns the corpus path and published contract of each
// packaged profile in path order. The semantic-comparison profiles have no
// published schema.
func packagedFiles() []packaged.File {
	return []packaged.File{
		{ContractID: "authoring-adapter-profile-v1", Path: "profiles/authoring-adapters/reference-v1.json"},
		{ContractID: contractBackendProfile, Path: "profiles/backend/full-remote-control-plane.json"},
		{ContractID: contractBackendProfile, Path: "profiles/backend/observability-evidence.json"},
		{ContractID: contractBackendProfile, Path: "profiles/backend/operation-supervision.json"},
		{ContractID: contractBackendProfile, Path: "profiles/backend/orchestration-capable.json"},
		{ContractID: contractBackendProfile, Path: "profiles/backend/orchestration-evaluation.json"},
		{ContractID: contractBackendProfile, Path: "profiles/backend/provisioning-only.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "history/participant-opacity-baseline-v1-sem-231-rev2.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "history/participant-opacity-runtime-reference-v1-sem-231-runtime-rev1.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "participant-crossing-dpbb-finite-v1.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "participant-crossing-multi-operation-dpbb-finite-v1.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "participant-opacity-baseline-v1.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "participant-opacity-runtime-reference-v1.json"},
		{ContractID: contractRelationProfile, Path: relationDir + "participant-opacity-theorem-v1.json"},
		{ContractID: "sdl-candidate-synthesis-profile-v1", Path: "profiles/candidate-synthesis/concept-nodes-v1.json"},
		{ContractID: "participant-boundary-flow-policy-v1", Path: "profiles/participant-boundary-flow-policy/participant-boundary-flow-policy-v1.json"},
		{ContractID: "participant-owner-flow-policy-v1", Path: "profiles/participant-boundary-flow-policy/participant-owner-flow-policy-v1.json"},
		{ContractID: "participant-control-teaching-profile-v1", Path: "profiles/participant-control/teaching-influence-rev1.json"},
		{ContractID: "participant-information-reconstruction-profile-v1", Path: "profiles/participant-information-reconstruction/occurrence-prefix-evidence-v1.json"},
		{ContractID: "random-stream-profile-v1", Path: "profiles/random-stream/blake3-xof-participant-v1.json"},
		{ContractID: "random-stream-profile-v1", Path: "profiles/random-stream/blake3-xof-v1.json"},
		{ContractID: "scientific-completeness-assessment-v1", Path: completenessDir + "delivery-assessment-2026-07-12.json"},
		{ContractID: "scientific-completeness-assessment-v1", Path: completenessDir + "delivery-assessment-2026-10-31.json"},
		{ContractID: "scientific-completeness-taxonomy-v1", Path: pathTaxonomy},
		{Path: comparisonDir + "reference-v1.json"},
		{Path: comparisonDir + "reference-v2.json"},
		{ContractID: "semantic-profile-v1", Path: "profiles/semantic/reference-stack-v1.json"},
		{ContractID: "validation-profile-catalog-v1", Path: pathValidation},
	}
}

func load(source fs.FS, schemas *validation.Validator) (*Profiles, error) {
	files := packagedFiles()
	contents, err := packaged.Read(source, schemas, files)
	if err != nil {
		return nil, damaged()
	}
	p := &Profiles{schemas: schemas}
	byPath := make(map[string][]byte, len(files))
	for i, file := range files {
		byPath[file.Path] = contents[i]
		if file.ContractID != "" {
			p.documents = append(p.documents, concept.Document{ContractID: file.ContractID, Path: file.Path, JSON: contents[i]})
		}
	}
	for _, step := range []func(map[string][]byte) error{p.decodeRelations, p.decodeValidation, p.decodeCompleteness, p.decodeComparisons} {
		if err := step(byPath); err != nil {
			return nil, err
		}
	}
	return p, nil
}

// decode reads a schema-checked document into its private wire form.
func decode(data []byte, target any) error {
	if json.Unmarshal(data, target) != nil {
		return damaged()
	}
	return nil
}

// decodeStrict reads a document that no published schema covers. It refuses
// members that the wire form does not declare.
func decodeStrict(data []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if decoder.Decode(target) != nil {
		return damaged()
	}
	return nil
}
