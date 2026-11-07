package governance

import (
	"context"
	"errors"
	"os"
	"slices"
	"strings"
)

const jsonArtifactCheck = "json-artifacts"
const jsonValidationRule = "json-schema-validation"

func (c *checker) jsonArtifacts(ctx context.Context, r *repository) (Report, error) {
	paths, err := r.changed(ctx, c.request)
	if err != nil {
		return Report{}, err
	}
	if len(paths) == 0 {
		paths = nil
	}
	targets, err := collectJSONTargets(r, paths)
	if err != nil {
		return Report{}, err
	}
	if len(targets) == 0 {
		return finish(nil), nil
	}
	if err := jsonWorkerSetting(); err != nil {
		return Report{}, err
	}
	failures := []Finding{}
	for _, batch := range jsonValidationBatches(targets) {
		if err := ctx.Err(); err != nil {
			return Report{}, err
		}
		if err := validateJSONBatch(r, batch); err != nil {
			if errors.Is(err, errSchemaPattern) {
				return Report{}, err
			}
			// The reference wraps check-jsonschema's implementation-specific prose.
			// Keep its rule, deterministic batch order and complete affected path set.
			failures = append(failures, finding(jsonValidationRule, strings.Join(batch.paths, ", ")+": schema validation failed", ""))
		}
	}
	return finish(failures), nil
}

type jsonValidationBatch struct {
	paths        []string
	schema, mode string
}

func jsonValidationBatches(targets []jsonTarget) []jsonValidationBatch {
	meta := []string{}
	groups := map[string][]string{}
	for _, target := range targets {
		switch target.mode {
		case jsonMetaschemaMode:
			meta = append(meta, target.path)
		case jsonSchemaMode:
			groups[target.schema] = append(groups[target.schema], target.path)
		}
	}
	batches := []jsonValidationBatch{}
	slices.Sort(meta)
	if len(meta) > 0 {
		batches = append(batches, jsonValidationBatch{paths: meta, mode: jsonMetaschemaMode})
	}
	keys := []string{}
	for schema := range groups {
		keys = append(keys, schema)
	}
	slices.Sort(keys)
	for _, schema := range keys {
		slices.Sort(groups[schema])
		batches = append(batches, jsonValidationBatch{groups[schema], schema, jsonSchemaMode})
	}
	return batches
}

func validateJSONBatch(r *repository, batch jsonValidationBatch) error {
	if batch.mode == jsonMetaschemaMode {
		return validateJSONMetaschemas(r, batch.paths)
	}
	value, err := readJSONArtifact(r, batch.schema)
	if err != nil {
		return err
	}
	schema, err := compileCandidate(value, false, true)
	if err != nil {
		return err
	}
	for _, name := range batch.paths {
		value, err := readJSONArtifact(r, name)
		if err != nil {
			return err
		}
		if err := schema.Validate(schemaTransport(value)); err != nil {
			return err
		}
	}
	return nil
}

func readJSONArtifact(r *repository, name string) (any, error) {
	if !regularRepoFile(r, name) {
		return nil, policyInputError("JSON source is not a regular in-repository file")
	}
	text, err := r.text(name)
	if err != nil {
		return nil, err
	}
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return nil, policyInputError(name + " is not UTF-8 JSON within the decoder limits")
	}
	if err := checkSchemaJSON(value); err != nil {
		return nil, err
	}
	return value, nil
}

func jsonWorkerSetting() error {
	value, set := os.LookupEnv("RAES_JSON_SCHEMA_WORKERS")
	if !set {
		return nil
	}
	integer, valid := pythonIntegerText(value)
	if !valid {
		return policyInputError("RAES_JSON_SCHEMA_WORKERS must be an integer")
	}
	text := integer
	if text == "0" || strings.HasPrefix(text, "-") {
		return policyInputError("RAES_JSON_SCHEMA_WORKERS must be at least one")
	}
	return nil
}

func validateJSONMetaschemas(r *repository, paths []string) error {
	for _, name := range paths {
		value, err := readJSONArtifact(r, name)
		if err != nil {
			return err
		}
		if err := checkCandidateMeta(value, false); err != nil {
			return err
		}
	}
	return nil
}
