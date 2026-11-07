package governance

import (
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"regexp"
	"slices"
)

const identityManifest = "tools/policy/historical_identity_records.json"
const identityManifestLimit = 1_000_000
const identityHistorical = "historical"

type identityRecord struct {
	path, category, label, digest string
	occurrences, suffix           *big.Int
}

type identityGroup struct {
	collection, classKey, category, label string
	classes                               []string
	generated                             bool
}

func identityGroups() []identityGroup {
	return []identityGroup{
		{"records", "record_class", identityHistorical, "historical record", []string{"accepted-adr", "dated-design-record", "historical-index", "lifecycle-record", "provenance-record", "release-history", "research-record"}, false},
		{"operational_bindings", "binding_class", "operational", "operational binding", []string{"external-service-project-key"}, false},
		{"generated_history_records", "record_class", "generated", "generated history record", []string{"generated-release-history"}, true},
	}
}

func identityFailure(rule, message, name string) Finding {
	return finding("identity-cutover-"+rule, message, name)
}

func identityManifestFailure(message string) Finding {
	return identityFailure("manifest", message, identityManifest)
}

func identityRecords(r *repository) (map[string]identityRecord, []Finding) {
	records := map[string]identityRecord{}
	raw, err := identityManifestObject(r)
	if err != nil {
		return records, []Finding{identityManifestFailure(err.Error())}
	}
	return identityManifestGroups(r, raw, records)
}

func identityManifestObject(r *repository) (*mapping, error) {
	if !r.file(identityManifest) {
		return nil, errors.New("missing or unsafe repository artifact " + pythonRepr(identityManifest))
	}
	data, err := r.readLimit(identityManifest, identityManifestLimit)
	if err != nil {
		return nil, err
	}
	value, err := decodeJSON(data, identityManifestLimit, true)
	if err != nil {
		return nil, err
	}
	raw, ok := value.(*mapping)
	if !ok {
		return nil, errors.New("manifest must contain a JSON object")
	}
	return raw, nil
}

func identityManifestGroups(r *repository, raw *mapping, records map[string]identityRecord) (map[string]identityRecord, []Finding) {
	findings := []Finding{}
	if raw.get("schema_version") != "historical-identity-records/v3" {
		findings = append(findings, identityManifestFailure("schema_version must be 'historical-identity-records/v3'"))
	}
	if raw.get("hash_algorithm") != sha256Algorithm {
		findings = append(findings, identityManifestFailure("hash_algorithm must be 'sha256'"))
	}
	groups := identityGroups()
	for _, group := range groups {
		if _, ok := raw.get(group.collection).([]any); !ok {
			return records, append(findings, identityManifestFailure(group.collection+" must be a list"))
		}
	}
	for _, group := range groups {
		entries, _ := raw.get(group.collection).([]any)
		for i, entry := range entries {
			record, failure := identityManifestEntry(r, entry, i, group, records)
			if failure != nil {
				findings = append(findings, *failure)
			} else {
				records[record.path] = record
			}
		}
	}
	return records, findings
}

func identityManifestEntry(r *repository, value any, index int, group identityGroup, seen map[string]identityRecord) (identityRecord, *Finding) {
	location := fmt.Sprintf("%s[%d]", group.collection, index)
	fail := func(message string) (identityRecord, *Finding) {
		f := identityManifestFailure(message)
		return identityRecord{}, &f
	}
	raw, ok := value.(*mapping)
	if !ok {
		return fail(location + " must be an object")
	}
	keys := []string{group.classKey, "content_sha256", "occurrences", "path", "rationale"}
	if group.generated {
		keys = append(keys, "classified_suffix_bytes")
	}
	slices.Sort(keys)
	if !mappingFields(raw, keys) {
		return fail(location + " must contain exactly " + pythonRepr(keys))
	}
	name, ok := raw.get("path").(string)
	if !ok || name == "" {
		return fail(location + ".path must be a non-empty string")
	}
	if _, exists := seen[name]; exists {
		label := "content-bound"
		if group.category == identityHistorical {
			label = "historical record"
		}
		return fail("duplicate " + label + " path " + pythonRepr(name))
	}
	if !r.safe(name) {
		failure := identityFailure("manifest-path", group.label+" path is unsafe", name)
		if group.category == identityHistorical {
			failure.Message = "historical path is unsafe"
		} else if group.generated {
			failure.Message = "generated history path is unsafe"
		}
		return identityRecord{}, &failure
	}
	return identityManifestContent(raw, location, name, group)
}

func identityManifestContent(raw *mapping, location, name string, group identityGroup) (identityRecord, *Finding) {
	fail := func(message string) (identityRecord, *Finding) {
		f := identityManifestFailure(location + message)
		return identityRecord{}, &f
	}
	class, ok := raw.get(group.classKey).(string)
	if !ok || !slices.Contains(group.classes, class) {
		return fail("." + group.classKey + " must be one of " + pythonRepr(group.classes))
	}
	if !nonemptyText(raw.get("rationale")) {
		return fail(".rationale must be non-empty")
	}
	occurrences, valid := positiveInteger(raw.get("occurrences"))
	if !valid {
		return fail(".occurrences must be a positive integer")
	}
	digest, ok := raw.get("content_sha256").(string)
	if !ok || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(digest) {
		return fail(".content_sha256 must be a lowercase sha256 digest")
	}
	var suffix *big.Int
	if group.generated {
		suffix, valid = positiveInteger(raw.get("classified_suffix_bytes"))
		if !valid {
			return fail(".classified_suffix_bytes must be a positive integer")
		}
	}
	return identityRecord{name, group.category, group.label, digest, occurrences, suffix}, nil
}

func positiveInteger(value any) (*big.Int, bool) {
	number, ok := value.(json.Number)
	if !ok {
		return nil, false
	}
	integer, valid := new(big.Int).SetString(string(number), 10)
	return integer, valid && integer.Sign() > 0
}

func mappingFields(raw *mapping, fields []string) bool {
	if raw.size() != len(fields) {
		return false
	}
	for _, field := range fields {
		if !raw.has(field) {
			return false
		}
	}
	return true
}
