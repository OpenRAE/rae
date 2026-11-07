package governance

import (
	"errors"
	"path"
	"path/filepath"
	"slices"
	"strings"
)

const schemasPrefix = "contracts/schemas/"
const jsonMetaschemaMode = "metaschema"
const jsonSchemaMode = "schema"
const profileSchemas = "profiles"

type jsonTarget struct{ path, schema, mode string }
type versionedRoute struct {
	prefix, family string
	recursive      bool
}

func versionedJSONRoutes() []versionedRoute {
	return []versionedRoute{
		{"contracts/profiles/semantic/", profileSchemas, false},
		{"contracts/profiles/backend/", profileSchemas, false},
		{"contracts/profiles/random-stream/", profileSchemas, false},
		{"contracts/profiles/participant-information-reconstruction/", profileSchemas, false},
		{"contracts/profiles/behavioral-relation/", profileSchemas, true},
		{"contracts/profiles/participant-boundary-flow-policy/", profileSchemas, false},
		{"contracts/profiles/scientific-completeness/", profileSchemas, false},
		{"contracts/profiles/validation/", profileSchemas, false},
		{"contracts/profiles/candidate-synthesis/", "candidate-synthesis", false},
		{"contracts/profiles/participant-control/", "participant-runtime", false},
		{"contracts/concept-authority/history/", "concept-authority", false},
		{"contracts/provenance/", provenanceField, false},
		{"contracts/realization-envelopes/", "realization-envelope", true},
		{"contracts/fixtures/random-stream-vectors/", profileSchemas, true},
	}
}

func collectJSONTargets(r *repository, paths []string) ([]jsonTarget, error) {
	if fullJSONValidation(paths) {
		paths = nil
	}
	targets := authoringJSONTargets(r, paths)
	versioned, err := versionedJSONTargets(r, paths)
	if err != nil {
		return nil, err
	}
	targets = append(targets, versioned...)
	if paths == nil {
		return dedupeJSONTargets(fullJSONTargets(r, targets)), nil
	}
	already := map[string]bool{}
	for _, target := range targets {
		already[target.path] = true
	}
	for _, name := range paths {
		if filepath.IsAbs(name) && outsideJSONRoot(r, name) {
			return nil, policyInputError("JSON artifact path is outside the repository")
		}
		if !already[name] && regularRepoFile(r, name) {
			if target := changedJSONTarget(name); target.mode != "" {
				targets = append(targets, target)
			}
		}
	}
	return dedupeJSONTargets(targets), nil
}

func fullJSONTargets(r *repository, targets []jsonTarget) []jsonTarget {
	for _, name := range discoverJSON(r, schemasPrefix, true) {
		targets = append(targets, jsonTarget{name, "", jsonMetaschemaMode})
	}
	for _, name := range discoverJSON(r, "contracts/concept-authority/", false) {
		targets = append(targets, changedJSONTarget(name))
	}
	fixtures := discoverJSON(r, "contracts/fixtures/", true)
	for _, directory := range []string{"valid", "migration", "context-invalid"} {
		for _, name := range fixtures {
			if path.Base(path.Dir(name)) == directory {
				targets = append(targets, jsonTarget{name, fixtureJSONSchema(name), jsonSchemaMode})
			}
		}
	}
	return targets
}

func fullJSONValidation(paths []string) bool {
	for _, name := range paths {
		if name == "tools/check_json_artifacts.py" {
			return true
		}
		for _, prefix := range []string{schemasPrefix, "implementations/python/packages/raes_contracts/", "implementations/python/packages/raes_backend_protocols/", "implementations/python/packages/raes_processor/", "implementations/python/packages/raes/", "tools/generate_contract_schemas.py"} {
			if strings.HasPrefix(name, prefix) {
				return true
			}
		}
	}
	return false
}

func authoringJSONTargets(r *repository, paths []string) []jsonTarget {
	targets := []jsonTarget{}
	for _, route := range []struct{ prefix, id string }{
		{"contracts/profiles/authoring-adapters/", "authoring-adapter-profile-v1"},
		{"contracts/fixtures/authoring-adapters-v1/cases/", "authoring-adapter-vector-v1"},
	} {
		for _, name := range jsonCandidates(r, paths, route.prefix, false) {
			targets = append(targets, jsonTarget{name, schemasPrefix + "authoring-adapters/" + route.id + ".json", jsonSchemaMode})
		}
	}
	return targets
}

func versionedJSONTargets(r *repository, paths []string) ([]jsonTarget, error) {
	frozen, err := frozenJSONRecords(r)
	if err != nil {
		return nil, err
	}
	targets := []jsonTarget{}
	for _, route := range versionedJSONRoutes() {
		for _, name := range jsonCandidates(r, paths, route.prefix, route.recursive) {
			if frozen[name] {
				continue
			}
			schema, schemaErr := versionedJSONSchema(r, name, route.family)
			if schemaErr != nil {
				return nil, schemaErr
			}
			targets = append(targets, jsonTarget{name, schema, jsonSchemaMode})
		}
	}
	return targets, nil
}

func versionedJSONSchema(r *repository, name, family string) (string, error) {
	text, err := r.text(name)
	if err != nil {
		if errors.Is(err, errNotUTF8) {
			return "", policyInputError(name + " is not UTF-8 JSON within the decoder limits")
		}
		return "", err
	}
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return "", policyInputError(name + " is not UTF-8 JSON within the decoder limits")
	}
	version, ok := object(value).get("schema_version").(string)
	if !ok {
		return "", policyInputError(name + " does not name a string schema_version")
	}
	return schemasPrefix + family + "/" + strings.ReplaceAll(version, "/", "-") + ".json", nil
}

func frozenJSONRecords(r *repository) (map[string]bool, error) {
	frozen := map[string]bool{}
	const name = "tools/policy/historical_identity_records.json"
	if !regularRepoFile(r, name) {
		return frozen, nil
	}
	text, err := r.text(name)
	if err != nil {
		return frozen, nil //nolint:nilerr // Unreadable manifests exclude nothing in the reference routing profile.
	}
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		if _, depth := errors.AsType[jsonDepthError](err); depth {
			return nil, err
		}
		return frozen, nil
	}
	rows, _ := object(value).get("records").([]any)
	for _, row := range rows {
		if name, ok := object(row).get("path").(string); ok {
			frozen[name] = true
		}
	}
	return frozen, nil
}

func changedJSONTarget(name string) jsonTarget {
	if !strings.HasSuffix(name, ".json") {
		return jsonTarget{}
	}
	switch {
	case strings.HasPrefix(name, schemasPrefix):
		return jsonTarget{name, "", jsonMetaschemaMode}
	case strings.HasPrefix(name, "contracts/concept-authority/"):
		return jsonTarget{name, schemasPrefix + "concept-authority/" + path.Base(name), jsonSchemaMode}
	case strings.HasPrefix(name, "contracts/fixtures/"):
		for _, directory := range []string{"/valid/", "/migration/", "/context-invalid/"} {
			if strings.Contains(name, directory) {
				return jsonTarget{name, fixtureJSONSchema(name), jsonSchemaMode}
			}
		}
	}
	return jsonTarget{}
}

func fixtureJSONSchema(name string) string {
	parts := strings.Split(prefixPath(strings.TrimPrefix(name, "contracts/fixtures/")), "/")
	category := parts[0]
	if category == "semantic-profile" {
		category = profileSchemas
	}
	return schemasPrefix + category + "/" + parts[1] + ".json"
}

func dedupeJSONTargets(targets []jsonTarget) []jsonTarget {
	seen := map[jsonTarget]bool{}
	ordered := make([]jsonTarget, 0, len(targets))
	for _, target := range targets {
		if !seen[target] {
			seen[target] = true
			ordered = append(ordered, target)
		}
	}
	slices.SortStableFunc(ordered, func(a, b jsonTarget) int {
		if mode := strings.Compare(a.mode, b.mode); mode != 0 {
			return mode
		}
		return strings.Compare(a.path, b.path)
	})
	return ordered
}

func jsonCandidates(r *repository, paths []string, prefix string, recursive bool) []string {
	if paths == nil {
		return discoverJSON(r, prefix, recursive)
	}
	candidates := []string{}
	for _, name := range paths {
		if !strings.HasPrefix(name, prefix) || !strings.HasSuffix(name, ".json") {
			continue
		}
		// Path.as_posix drops empty and dot components, but retains '..'.
		name = prefixPath(name)
		if regularRepoFile(r, name) {
			candidates = append(candidates, name)
		}
	}
	return candidates
}

func outsideJSONRoot(r *repository, name string) bool {
	root := prefixPath(filepath.ToSlash(r.absolute))
	absolute := prefixPath(filepath.ToSlash(name))
	return root != "" && absolute != root && !strings.HasPrefix(absolute, root+"/")
}
