package concept

import (
	"encoding/json"
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/packaged"
)

const (
	contractRelations  = "behavioral-relations-v1"
	pathRelations      = "concept-authority/behavioral-relations-v1.json"
	pathFamilies       = "concept-authority/concept-families-v1.json"
	pathVocabularies   = "concept-authority/controlled-vocabularies-v1.json"
	relationHistoryDir = "concept-authority/history/behavioral-relations-v1-"
)

// historyRevisions returns the registered history revisions of the taxonomy.
func historyRevisions() []string { return []string{"rev8", "rev9", "rev10", "rev11", "rev12", "rev13"} }

// packagedFiles returns the corpus path and published contract of each
// packaged concept-authority document, in path order.
func packagedFiles() []packaged.File {
	files := []packaged.File{
		{ContractID: "atlas-tactics-source-v1", Path: "concept-authority/atlas-tactics-source-v1.json"},
		{ContractID: "attack-enterprise-tactics-source-v1", Path: "concept-authority/attack-enterprise-tactics-source-v1.json"},
		{ContractID: contractRelations, Path: pathRelations},
		{ContractID: "concept-families-v1", Path: pathFamilies},
		{ContractID: "controlled-vocabularies-v1", Path: pathVocabularies},
		{ContractID: "fipa-communicative-acts-source-v1", Path: "concept-authority/fipa-communicative-acts-source-v1.json"},
	}
	for _, revision := range []string{"rev10", "rev11", "rev12", "rev13", "rev8", "rev9"} {
		files = append(files, packaged.File{ContractID: contractRelations, Path: relationHistoryDir + revision + ".json"})
	}
	return append(files,
		packaged.File{ContractID: "nist-csf-defensive-categories-source-v1", Path: "concept-authority/nist-csf-defensive-categories-source-v1.json"},
		packaged.File{ContractID: "reference-models-v1", Path: "concept-authority/reference-models-v1.json"},
		packaged.File{ContractID: "uco-alignment-v1", Path: "concept-authority/uco-alignment-v1.json"},
		packaged.File{ContractID: "w3c-activitystreams-activity-types-source-v1", Path: "concept-authority/w3c-activitystreams-activity-types-source-v1.json"},
	)
}

func load(source fs.FS, schemas *validation.Validator) (*Authority, error) {
	files := packagedFiles()
	contents, err := packaged.Read(source, schemas, files)
	if err != nil {
		return nil, damaged()
	}
	a := &Authority{schemas: schemas}
	byPath := make(map[string][]byte, len(files))
	for i, file := range files {
		byPath[file.Path] = contents[i]
		a.documents = append(a.documents, Document{ContractID: file.ContractID, Path: file.Path, JSON: contents[i]})
	}
	for _, step := range []func(map[string][]byte) error{a.decodeVocabularies, a.decodeFamilies, a.decodeRelations, a.decodeSnapshots} {
		if err := step(byPath); err != nil {
			return nil, err
		}
	}
	return a, nil
}

// decode reads a schema-checked document into its private wire form.
func decode(data []byte, target any) error {
	if json.Unmarshal(data, target) != nil {
		return damaged()
	}
	return nil
}
