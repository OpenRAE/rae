package governance

import (
	"fmt"
	"slices"
	"strings"
)

const uncoveredCoverage = "uncovered"

const schemaCoverageCheck = "schema-coverage"
const coverageCatalogRule = "schema-coverage-catalog-unreadable"
const coverageDeclarationRule = "schema-coverage-declaration-invalid"
const coverageMissingRule = "schema-coverage-missing"
const assuranceFulfillmentPath = "specs/formal/assurance-fulfillment.yaml"

type coverageRow struct{ id, path, leg string }

func (c *checker) schemaCoverage(r *repository) (Report, error) {
	rows, findings, err := classifyCoverage(r)
	if err != nil {
		return Report{}, err
	}
	if c.request.Mode == Inventory {
		return Report{Findings: []Finding{}, Text: coverageInventory(rows, findings)}, nil
	}
	for _, row := range rows {
		if row.leg == uncoveredCoverage {
			findings = append(findings, finding(coverageMissingRule, "published schema "+row.id+" has no fixture, formal, or declared coverage evidence", row.path))
		}
	}
	sortFindings(findings)
	return c.finish(r, findings)
}

func classifyCoverage(r *repository) ([]coverageRow, []Finding, error) {
	catalog, err := publicationCatalog(r)
	if err != nil {
		return nil, []Finding{finding(coverageCatalogRule, "schema publication catalog could not be read; check_schema_publication.py owns the detail", publicationManifest)}, nil //nolint:nilerr // The reference turns catalog read errors into this gate finding.
	}
	entries, ok := catalog.get("schemas").([]any)
	if !ok {
		return nil, []Finding{finding(coverageCatalogRule, "schema publication catalog defines no schemas array", publicationManifest)}, nil
	}
	targets, err := collectJSONTargets(r, nil)
	if err != nil {
		return nil, nil, err
	}
	corpus := map[string]bool{}
	for _, target := range targets {
		if target.mode == jsonSchemaMode {
			corpus[target.schema] = true
		}
	}
	formal, findings := formalCoveragePaths(r)
	rows := []coverageRow{}
	for _, value := range entries {
		row, declared, err := classifyCoverageEntry(r, object(value), corpus, formal)
		if err != nil {
			return nil, nil, err
		}
		findings = append(findings, declared...)
		if row != nil {
			rows = append(rows, *row)
		}
	}
	slices.SortFunc(rows, func(a, b coverageRow) int {
		if d := strings.Compare(a.id, b.id); d != 0 {
			return d
		}
		if d := strings.Compare(a.path, b.path); d != 0 {
			return d
		}
		return strings.Compare(a.leg, b.leg)
	})
	return rows, findings, nil
}

func formalCoveragePaths(r *repository) (map[string]bool, []Finding) {
	paths := map[string]bool{}
	if !r.file(assuranceFulfillmentPath) {
		return paths, nil
	}
	text, err := r.text(assuranceFulfillmentPath)
	var value any
	if err == nil {
		value, err = yamlValue([]byte(text), true)
	}
	if err != nil {
		return paths, []Finding{finding(coverageCatalogRule, "assurance fulfillment map is not readable valid YAML", assuranceFulfillmentPath)}
	}
	entries, _ := object(value).get("entries").([]any)
	for _, entry := range entries {
		artifacts, _ := object(entry).get("delivered_artifacts").([]any)
		for _, artifact := range artifacts {
			if name, ok := object(artifact).get("path").(string); ok {
				paths[name] = true
			}
		}
	}
	return paths, nil
}

func coverageInventory(rows []coverageRow, findings []Finding) string {
	lines := []string{"Published-schema coverage report (ASR-501)", ""}
	for _, leg := range []string{"corpus", "formal", "declared", uncoveredCoverage} {
		group := []coverageRow{}
		for _, row := range rows {
			if row.leg == leg {
				group = append(group, row)
			}
		}
		lines = append(lines, fmt.Sprintf("## %s (%d)", leg, len(group)))
		for _, row := range group {
			lines = append(lines, "  - "+row.id+": "+row.path)
		}
		lines = append(lines, "")
	}
	if len(findings) > 0 {
		lines = append(lines, fmt.Sprintf("## malformed associations (%d)", len(findings)))
		for _, f := range findings {
			lines = append(lines, "  - "+renderFinding(f))
		}
		lines = append(lines, "")
	}
	return strings.TrimRightFunc(strings.Join(lines, "\n"), pythonWhitespace) + "\n"
}

func classifyCoverageEntry(r *repository, entry *mapping, corpus, formal map[string]bool) (*coverageRow, []Finding, error) {
	id, idOK := entry.get("contract_id").(string)
	name, pathOK := entry.get("schema_path").(string)
	if !idOK || !pathOK {
		return nil, nil, nil
	}
	leg := uncoveredCoverage
	if corpus[name] {
		leg = "corpus"
	} else if formal[name] {
		leg = "formal"
	}
	if !entry.has("coverage") {
		return &coverageRow{id, name, leg}, nil, nil
	}
	qualified, findings, err := coverageDeclaration(r, entry.get("coverage"), id, name)
	if err != nil {
		return nil, nil, err
	}
	if leg == uncoveredCoverage && qualified {
		leg = "declared"
	}
	return &coverageRow{id, name, leg}, findings, nil
}
