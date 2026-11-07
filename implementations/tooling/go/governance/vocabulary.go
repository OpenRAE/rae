package governance

import (
	"context"
	"crypto/sha256"
	"fmt"
	"path"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

const attackVocabulary = "ATT&CK"
const atlasVocabulary = "ATLAS"
const activityVocabulary = "ActivityStreams"
const atlasMatrixID = "ATLAS-matrix"
const tacticIDField = "tactic_id"
const urlField = "url"
const nameField = "name"
const uuidField = "uuid"
const shortnameField = "shortname"

const vocabularyCatalogPath = "contracts/concept-authority/controlled-vocabularies-v1.json"

type vocabularyField struct{ name, value string }
type vocabularyCitation struct{ url, sourceMessage, catalogMessage string }
type vocabularyProfile struct {
	path, label, id string
	fields          []vocabularyField
	citations       []vocabularyCitation
}

func (p vocabularyProfile) value(name string) string {
	for _, field := range p.fields {
		if field.name == name {
			return field.value
		}
	}
	return ""
}

func (c *checker) vocabulary(ctx context.Context, r *repository) (Report, error) {
	findings := []Finding{}
	inputs := []vocabularyInput{}
	for _, profile := range vocabularyProfiles(c.request.Tool) {
		input, messages, err := c.localVocabulary(r, profile)
		if err != nil {
			return c.vocabularyError(err)
		}
		inputs = append(inputs, input)
		for _, message := range messages {
			findings = append(findings, finding(c.request.Tool, message, ""))
		}
	}
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	if c.request.VerifyRemote {
		messages, err := c.remoteVocabularies(ctx, r, inputs)
		if err != nil {
			return c.vocabularyError(err)
		}
		for _, message := range messages {
			findings = append(findings, finding(c.request.Tool, message, ""))
		}
	}
	return finish(findings), nil
}

func (c *checker) localVocabulary(r *repository, profile vocabularyProfile) (vocabularyInput, []string, error) {
	source, err := c.vocabularyModel(r, profile.path)
	if err != nil {
		return vocabularyInput{}, nil, err
	}
	input := vocabularyInput{profile: profile, source: source}
	var catalog *mapping
	if profile.id != "" {
		catalog, err = c.vocabularyModel(r, vocabularyCatalogPath)
		if err != nil {
			return input, nil, err
		}
	}
	messages, err := vocabularySource(profile, source)
	if err != nil {
		return input, nil, err
	}
	return input, append(messages, vocabularyCatalog(profile, source, catalog)...), nil
}

func (c *checker) vocabularyError(err error) (Report, error) {
	if category, known := fault.CategoryOf(err); known && category == fault.InvalidInput {
		return finish([]Finding{finding(c.request.Tool, err.Error(), "")}), nil
	}
	return Report{}, err
}

func (c *checker) vocabularyModel(r *repository, name string) (*mapping, error) {
	text, err := r.text(name)
	if err != nil {
		return nil, policyInputError(name + ": cannot read UTF-8 source")
	}
	ordered, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return nil, policyInputError(name + ": " + err.Error())
	}
	// The reference JSON loader retains the last duplicate member. Normalize
	// that transport before handing it to the stricter public admission owner;
	// keep the ordered view separately for vocabulary order comparisons.
	data, err := canonjson.Sorted([]byte(text), true)
	if err != nil {
		return nil, err
	}
	id := strings.TrimSuffix(path.Base(name), ".json")
	data, err = normalizeVocabularyPositions(id, data, object(ordered))
	if err != nil {
		return nil, err
	}
	data, err = normalizeConceptCatalog(id, data)
	if err != nil {
		return nil, err
	}
	if _, validationErr := c.validateContract(id, data); validationErr != nil {
		return nil, fmt.Errorf("%s: %w", name, validationErr)
	}
	raw, ok := ordered.(*mapping)
	if !ok {
		return nil, policyInputError(name + ": expected an object")
	}
	return raw, nil
}

func vocabularySource(profile vocabularyProfile, source *mapping) ([]string, error) {
	findings := vocabularyFields(profile.path+": ", source, profile.fields)
	findings = append(findings, vocabularyCitations(profile, source, false)...)
	switch profile.label {
	case nistVocabulary:
		rows, _ := source.get("categories").([]any)
		categories := make([]map[string]string, len(rows))
		for i, row := range rows {
			categories[i] = map[string]string{}
			for _, field := range []string{"category_id", "term_id", titleField, descriptionField, "function"} {
				categories[i][field] = pythonStr(object(row).get(field))
			}
		}
		data, err := canonicalJSON(categories, true)
		if err != nil {
			return nil, err
		}
		if "sha256:"+fmt.Sprintf("%x", sha256.Sum256(data)) != source.get(sourceDigestField) {
			findings = append(findings, profile.path+": source_digest does not match the canonical category snapshot")
		}
	case activityVocabulary, fipaVocabulary:
		findings = append(findings, autonomousVocabulary(profile, source)...)
	}
	return findings, nil
}

func vocabularyFields(prefix string, actual *mapping, expected []vocabularyField) []string {
	findings := []string{}
	for _, field := range expected {
		if actual.get(field.name) != field.value {
			findings = append(findings, prefix+field.name+" is "+pythonRepr(actual.get(field.name))+"; expected "+pythonRepr(field.value))
		}
	}
	return findings
}

func vocabularyCitations(profile vocabularyProfile, source *mapping, catalog bool) []string {
	citations, _ := stringList(source.get("citation_urls"), false)
	findings := []string{}
	for _, citation := range profile.citations {
		prefix, message := profile.path+": ", citation.sourceMessage
		if catalog {
			prefix, message = vocabularyCatalogPath+": "+profile.id+".source.", citation.catalogMessage
		}
		if message != "" && !slices.Contains(citations, citation.url) {
			findings = append(findings, prefix+message)
		}
	}
	return findings
}

func object(value any) *mapping {
	m, _ := value.(*mapping)
	return m
}

func rowStrings(source *mapping, field, key string) []string {
	rows, _ := source.get(field).([]any)
	values := make([]string, len(rows))
	for i, row := range rows {
		values[i], _ = object(row).get(key).(string)
	}
	return values
}

func autonomousVocabulary(profile vocabularyProfile, source *mapping) []string {
	findings := []string{}
	if profile.label == fipaVocabulary {
		expected := strings.Fields("accept-proposal agree cancel cfp confirm disconfirm failure inform inform-if inform-ref not-understood propagate propose proxy query-if query-ref refuse reject-proposal request request-when request-whenever subscribe")
		if !slices.Equal(rowStrings(source, "communicative_acts", "concept_id"), expected) {
			findings = append(findings, profile.path+": communicative act order/content differs from SC00037J")
		}
		return findings
	}
	expected := activityTypeNames()
	if !slices.Equal(rowStrings(source, "activity_types", "type_name"), expected) {
		findings = append(findings, profile.path+": activity type order/content differs from the dated Recommendation")
	}
	for i, name := range expected {
		expected[i] = "https://www.w3.org/ns/activitystreams#" + name
	}
	if !slices.Equal(rowStrings(source, "activity_types", "concept_id"), expected) {
		findings = append(findings, profile.path+": concept ids differ from the normative Activity type IRIs")
	}
	return findings
}

func activityTypeNames() []string {
	return strings.Fields("Accept Add Announce Arrive Block Create Delete Dislike Flag Follow Ignore Invite Join Leave Like Listen Move Offer Question Reject Read Remove TentativeReject TentativeAccept Travel Undo Update View")
}
