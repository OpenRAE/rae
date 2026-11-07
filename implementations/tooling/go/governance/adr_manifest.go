package governance

import (
	"fmt"
	"regexp"
)

func malformedADR(message string) Finding {
	return finding("adr-manifest-malformed", message, adrManifest)
}

func readADRPins(r *repository) ([]adrPin, []Finding) {
	if !r.file(adrManifest) {
		return nil, []Finding{malformedADR("ADR pin manifest is missing")}
	}
	data, err := r.read(adrManifest)
	if err != nil {
		return nil, []Finding{malformedADR("ADR pin manifest is not valid YAML")}
	}
	raw, err := yamlValue(data, true)
	if err != nil {
		return nil, []Finding{malformedADR("ADR pin manifest is not valid YAML")}
	}
	return coerceADRPins(raw)
}

func coerceADRPins(raw any) ([]adrPin, []Finding) {
	root, ok := raw.(*mapping)
	if !ok {
		return nil, []Finding{malformedADR("manifest root must be a mapping")}
	}
	if root.get("hash_algorithm") != sha256Algorithm {
		return nil, []Finding{malformedADR("hash_algorithm must be 'sha256'; got " + pythonRepr(root.get("hash_algorithm")))}
	}
	entries, ok := root.get("adrs").([]any)
	if !ok {
		return nil, []Finding{malformedADR("'adrs' must be a list")}
	}
	pins, findings := []adrPin{}, []Finding{}
	seen := map[string]bool{}
	for i, value := range entries {
		pin, failures := coerceADRPin(value, i, seen)
		if len(failures) > 0 {
			findings = append(findings, failures...)
		} else {
			pins = append(pins, pin)
		}
	}
	if len(findings) > 0 {
		return nil, findings
	}
	return pins, findings
}

func coerceADRPin(value any, index int, seen map[string]bool) (adrPin, []Finding) {
	fail := func(message string) (adrPin, []Finding) { return adrPin{}, []Finding{malformedADR(message)} }
	entry, ok := value.(*mapping)
	if !ok {
		return fail(fmt.Sprintf("adrs[%d] must be a mapping", index))
	}
	id, ok := entry.get("id").(string)
	if !ok || !regexp.MustCompile(`^ADR-\p{Nd}{3}\n?$`).MatchString(id) {
		return fail(fmt.Sprintf("adrs[%d].id must match ADR-NNN; got %s", index, pythonRepr(entry.get("id"))))
	}
	if seen[id] {
		return fail("duplicate manifest entry for " + id)
	}
	seen[id] = true
	name, ok := entry.get("path").(string)
	if !ok || name == "" {
		return fail(id + ": path must be a non-empty string")
	}
	pin, ok := entry.get("pin").(string)
	if !ok || !regexp.MustCompile(`^[0-9a-f]{64}\n?$`).MatchString(pin) {
		return fail(id + ": pin must be a 64-character sha256 hex digest")
	}
	refs, failures := coerceADRAmendments(id, entry.get("amendments"))
	return adrPin{id: id, path: name, pin: pin, refs: refs}, failures
}

func coerceADRAmendments(id string, value any) ([]string, []Finding) {
	refs := []string{}
	if !truth(value) {
		return refs, nil
	}
	items, ok := value.([]any)
	if !ok {
		return nil, []Finding{malformedADR(id + ": amendments must be a list")}
	}
	for i, item := range items {
		row, rowOK := item.(*mapping)
		ref, refOK := row.get("ref").(string)
		if !rowOK || !refOK {
			return nil, []Finding{malformedADR(fmt.Sprintf("%s: amendments[%d] must be a mapping with a string 'ref'", id, i))}
		}
		refs = append(refs, ref)
	}
	return refs, nil
}
