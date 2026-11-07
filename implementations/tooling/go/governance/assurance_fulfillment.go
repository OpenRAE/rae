package governance

import (
	"io/fs"
	"path"
	"slices"
	"strconv"
)

type fulfillmentRegistry struct {
	levels     map[string]string
	ids, paths []string
}

func fulfillmentFinding(rule, message string) Finding {
	return finding("assurance-fulfillment-"+rule, message, assuranceFulfillment)
}

func assuranceFulfillmentFindings(r *repository, levels []any) ([]Finding, error) {
	raw, findings, err := assuranceYAML(r, assuranceFulfillment, "assurance-fulfillment", "assurance fulfillment map")
	if err != nil || raw == nil {
		return findings, err
	}
	findings = append(findings, assuranceFulfillmentTop(raw)...)
	required, kinds := assuranceRequired(levels)
	domains, err := assuranceFormalDomains(r)
	if err != nil {
		return nil, err
	}
	registry, problems := assuranceSubsystemRegistry(r, raw, required, domains)
	findings = append(findings, problems...)
	for _, domain := range domains {
		if !slices.Contains(registry.paths, domain) {
			findings = append(findings, fulfillmentFinding("coverage", "classified formal subsystem is absent from the fulfillment registry: "+domain))
		}
	}
	return append(findings, assuranceFulfillmentEntries(r, raw, registry, required, kinds)...), nil
}
func assuranceFulfillmentTop(raw *mapping) []Finding {
	findings := []Finding{}
	if raw.get("fulfillment") != "classification-based-assurance-fulfillment" {
		findings = append(findings, fulfillmentFinding("field", "fulfillment field must be 'classification-based-assurance-fulfillment'"))
	}
	if raw.get("policy_ref") != assurancePolicy {
		findings = append(findings, fulfillmentFinding("field", "policy_ref must be "+assurancePolicy))
	}
	if _, ok := raw.get(adrRefsField).([]any); !ok {
		findings = append(findings, fulfillmentFinding("field", "adr_refs must be a YAML list"))
	} else {
		for _, id := range []string{"ADR-007", "ADR-018"} {
			if !slices.Contains(assuranceStrings(raw.get(adrRefsField)), id) {
				findings = append(findings, fulfillmentFinding("field", "adr_refs must include "+id))
			}
		}
	}
	return findings
}

func assuranceFormalDomains(r *repository) ([]string, error) {
	const root = "specs/formal"
	if !boundaryDirectory(r, root) {
		return []string{}, nil
	}
	resolved, err := r.resolve(root)
	if err != nil {
		return nil, err
	}
	entries, err := fs.ReadDir(r.root.FS(), resolved)
	if err != nil {
		return nil, err
	}
	domains := []string{}
	for _, entry := range entries {
		name := path.Join(root, entry.Name())
		if secretPath(name) {
			return nil, errUnsafePath
		}
		if boundaryDirectory(r, name) && r.file(path.Join(name, "README.md")) {
			domains = append(domains, name)
		}
	}
	return domains, nil
}

func assuranceSubsystemRegistry(r *repository, raw *mapping, required map[string][]string, domains []string) (fulfillmentRegistry, []Finding) {
	registry := fulfillmentRegistry{levels: map[string]string{}, ids: []string{}, paths: []string{}}
	findings := []Finding{}
	subsystems, ok := raw.get("subsystems").([]any)
	if !ok {
		findings = append(findings, fulfillmentFinding("field", "subsystems must be a YAML list"))
	}
	seen := map[string]bool{}
	for i, value := range subsystems {
		index := "subsystems[" + strconv.Itoa(i) + "]"
		sub := object(value)
		if sub == nil {
			findings = append(findings, fulfillmentFinding("subsystem", index+" must be a mapping"))
			continue
		}
		id, textual := sub.get("id").(string)
		validID := textual && assuranceNonblank(id)
		ident := id
		switch {
		case !validID:
			ident = index
			findings = append(findings, fulfillmentFinding("subsystem", index+".id must be a non-empty string"))
		case seen[id]:
			findings = append(findings, fulfillmentFinding("subsystem", "duplicate subsystem id: "+id))
		default:
			seen[id] = true
		}
		relative, problem := assuranceSubsystemPath(r, ident, sub.get("path"), domains, registry.paths)
		if problem != nil {
			findings = append(findings, *problem)
		} else {
			registry.paths = append(registry.paths, relative)
		}
		level, textual := sub.get("fm_level").(string)
		_, known := required[level]
		if !textual || !known {
			findings = append(findings, fulfillmentFinding("level", ident+".fm_level "+pythonRepr(sub.get("fm_level"))+" is not defined in "+assurancePolicy))
			level = ""
		}
		if validID {
			registry.record(id, level)
		}
	}
	return registry, findings
}

func assuranceSubsystemPath(r *repository, id string, value any, domains, registered []string) (string, *Finding) {
	message := ""
	relative := ""
	if !assuranceNonblank(value) {
		message = id + ".path must be a non-empty repo-relative path"
	} else {
		selected := pythonStr(value)
		resolved, err := r.resolve(selected)
		switch {
		case err != nil:
			message = id + ".path escapes the repo root: " + selected
		case !slices.Contains(domains, resolved):
			message = id + ".path is not a classified formal-spec domain (must be an immediate specs/formal/<domain>/ directory containing README.md): " + selected
		case slices.Contains(registered, resolved):
			message = id + ".path duplicates another registry entry's path: " + selected
		default:
			relative = resolved
		}
	}
	if message == "" {
		return relative, nil
	}
	result := fulfillmentFinding("subsystem", message)
	return "", &result
}

func assuranceFulfillmentEntries(r *repository, raw *mapping, registry fulfillmentRegistry, required map[string][]string, kinds []string) []Finding {
	findings := []Finding{}
	entries, ok := raw.get("entries").([]any)
	if !ok {
		findings = append(findings, fulfillmentFinding("field", "entries must be a YAML list"))
	}
	seen := []string{}
	for i, value := range entries {
		entry := object(value)
		prefix := "entries[" + strconv.Itoa(i) + "]"
		if entry == nil {
			findings = append(findings, fulfillmentFinding("entry", prefix+" must be a mapping"))
			continue
		}
		id, _ := entry.get("subsystem").(string)
		if !assuranceNonblank(entry.get("subsystem")) {
			findings = append(findings, fulfillmentFinding("entry", prefix+".subsystem must be a non-empty string"))
			continue
		}
		if slices.Contains(seen, id) {
			findings = append(findings, fulfillmentFinding("entry", "duplicate fulfillment entry for subsystem: "+id))
			continue
		}
		seen = append(seen, id)
		level, known := registry.levels[id]
		if !known {
			findings = append(findings, fulfillmentFinding("entry-unknown", "fulfillment entry references subsystem "+pythonRepr(id)+" not in the registry"))
			continue
		}
		findings = append(findings, assuranceFulfillmentEvidence(r, id, level, entry, required, kinds)...)
	}
	for _, id := range registry.ids {
		if !slices.Contains(seen, id) {
			findings = append(findings, fulfillmentFinding("entry-missing", "classified subsystem "+pythonRepr(id)+" is in the registry but has no fulfillment entry"))
		}
	}
	return findings
}

func assuranceFulfillmentEvidence(r *repository, id, level string, entry *mapping, required map[string][]string, kinds []string) []Finding {
	findings := []Finding{}
	delivered, problems := assuranceFulfillmentDelivered(r, id, entry.get("delivered_artifacts"), kinds)
	findings = append(findings, problems...)
	waived, problems := assuranceFulfillmentWaived(id, entry.get("waived_artifacts"), kinds)
	findings = append(findings, problems...)
	if level != "" {
		if missing := stringDifference(required[level], delivered, waived); len(missing) > 0 {
			findings = append(findings, fulfillmentFinding("artifacts", id+" ("+level+") must deliver or waive required artifact kind(s): "+pythonRepr(missing)))
		}
	}
	return findings
}

func (r *fulfillmentRegistry) record(id, level string) {
	if _, exists := r.levels[id]; !exists {
		r.levels[id] = level
		r.ids = append(r.ids, id)
	}
}
