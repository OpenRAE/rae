package sdl

import (
	"context"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const instantiatedSnapshotProfile = "raes-sdl-instantiated-snapshot/v2"
const currentSnapshotProfile = "raes-sdl-instantiated-snapshot/v3"

// AdmitSnapshotWithContext authenticates a snapshot join and admits its native
// instantiated scenario. Historical VM and empty-classification migrations are
// confined to this boundary; their original digest must match before migration.
//
//nolint:ireturn // Returns the sealed native instantiated phase handle.
func AdmitSnapshotWithContext(ctx context.Context, data []byte, expectedDigest string) (InstantiatedScenario, error) {
	if err := checkParsingContext(ctx); err != nil {
		return nil, err
	}
	value, err := ingress.Parse(data, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}, ingress.Object)
	if err != nil {
		return nil, err
	}
	snapshot := snapshotObject(value)
	scenario := snapshotObject(snapshot["scenario"])
	profile := snapshot["profile"]
	if len(snapshot) != 2 || (profile != instantiatedSnapshotProfile && profile != currentSnapshotProfile) || scenario == nil {
		return nil, invalidScenario()
	}
	if profile == currentSnapshotProfile {
		return admitSnapshotScenario(ctx, scenario, expectedDigest, true, currentSnapshotProfile)
	}
	original, err := snapshotHash(snapshot)
	if err != nil {
		return nil, err
	}
	historical, err := historicalSnapshotHash(snapshot, scenario)
	if err != nil {
		return nil, err
	}
	changed, err := migrateSnapshotVM(scenario)
	if err != nil {
		return nil, err
	}
	changed = cleanSnapshotClassifications(scenario) || changed
	if changed && expectedDigest != original && expectedDigest != historical {
		return nil, invalidScenario()
	}
	return admitSnapshotScenario(ctx, scenario, expectedDigest, !changed, instantiatedSnapshotProfile)
}

func snapshotObject(value any) map[string]any { result, _ := value.(map[string]any); return result }
func snapshotArray(value any) []any           { result, _ := value.([]any); return result }
func snapshotHash(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", invalidScenario()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", err
	}
	return digest.SHA256(canonical), nil
}
func historicalSnapshotHash(snapshot, scenario map[string]any) (string, error) {
	projected := maps.Clone(snapshot)
	payload := maps.Clone(scenario)
	nodes := maps.Clone(snapshotObject(scenario["nodes"]))
	for name, raw := range nodes {
		node := snapshotObject(raw)
		if node == nil {
			continue
		}
		node = maps.Clone(node)
		if _, present := node["architecture"]; !present {
			node["architecture"] = nil
		}
		nodes[name] = node
	}
	if nodes != nil {
		payload["nodes"] = nodes
	}
	projected["scenario"] = payload
	return snapshotHash(projected)
}
func migrateSnapshotVM(scenario map[string]any) (bool, error) {
	nodes := snapshotObject(scenario["nodes"])
	names := []string{}
	for name, raw := range nodes {
		if snapshotObject(raw)["type"] == "vm" {
			names = append(names, name)
		}
	}
	if len(names) == 0 {
		return false, nil
	}
	slices.Sort(names)
	provenance := snapshotObject(scenario["instantiation_provenance"])
	if provenance == nil {
		return false, invalidScenario()
	}
	constraints := []any{}
	if raw, present := provenance["realization_constraints"]; present {
		var ok bool
		constraints, ok = raw.([]any)
		if !ok {
			return false, invalidScenario()
		}
	}
	for _, name := range names {
		pointer := "/nodes/" + jsonpointer.EscapeToken(name)
		if snapshotConstraintCollision(constraints, pointer) {
			return false, invalidScenario()
		}
		snapshotObject(nodes[name])["type"] = "compute"
		constraints = append(constraints, map[string]any{"namespace": []any{}, "field_pointer": pointer, "concern": "compute-substrate", "posture": "exact", "domain": map[string]any{"kind": "exact", "value": "virtual-machine"}, "provenance": "legacy-node-type-vm"})
	}
	provenance["realization_constraints"] = constraints
	return true, nil
}
func snapshotConstraintCollision(constraints []any, pointer string) bool {
	for _, raw := range constraints {
		constraint := snapshotObject(raw)
		if len(snapshotArray(constraint["namespace"])) == 0 && constraint["field_pointer"] == pointer && constraint["concern"] == "compute-substrate" {
			return true
		}
	}
	return false
}
func removeEmptySnapshotFields(value map[string]any, names []string, mapping bool) bool {
	changed := false
	for _, name := range names {
		raw, present := value[name]
		if !present {
			continue
		}
		var empty bool
		if mapping {
			entry, ok := raw.(map[string]any)
			empty = ok && len(entry) == 0
		} else {
			entry, ok := raw.([]any)
			empty = ok && len(entry) == 0
		}
		if empty {
			delete(value, name)
			changed = true
		}
	}
	return changed
}
func cleanSnapshotClassifications(scenario map[string]any) bool {
	changed := removeEmptySnapshotFields(scenario, []string{legacyVulnerabilitiesField}, true)
	sections := map[string][]string{"nodes": {legacyVulnerabilitiesField}, "features": {legacyVulnerabilitiesField}, "action_contracts": {"external_mappings"}, "behavior_specifications": {"offensive_behavior_refs", "ai_offensive_behavior_refs", "defensive_behavior_refs"}}
	for section, names := range sections {
		for _, raw := range snapshotObject(scenario[section]) {
			changed = removeEmptySnapshotFields(snapshotObject(raw), names, false) || changed
		}
	}
	changed = cleanSnapshotEntities(snapshotObject(scenario["entities"])) || changed
	return cleanSnapshotRoutes(snapshotObject(scenario["nodes"])) || changed
}
func cleanSnapshotEntities(entities map[string]any) bool {
	changed := false
	for _, raw := range entities {
		entity := snapshotObject(raw)
		changed = removeEmptySnapshotFields(entity, []string{legacyVulnerabilitiesField, "categories"}, false) || changed
		changed = cleanSnapshotEntities(snapshotObject(entity["entities"])) || changed
	}
	return changed
}
func cleanSnapshotRoutes(nodes map[string]any) bool {
	changed := false
	for _, raw := range nodes {
		runtime := snapshotObject(snapshotObject(raw)["runtime"])
		for _, app := range snapshotArray(runtime["applications"]) {
			for _, route := range snapshotArray(snapshotObject(app)["routes"]) {
				changed = removeEmptySnapshotFields(snapshotObject(route), []string{"vulnerability_refs"}, false) || changed
			}
		}
	}
	return changed
}

//nolint:ireturn // Returns a sealed native instantiated phase.
func admitSnapshotScenario(ctx context.Context, scenario map[string]any, expectedDigest string, verifyDigest bool, profile string) (InstantiatedScenario, error) {
	raw, err := json.Marshal(scenario)
	if err != nil {
		return nil, invalidScenario()
	}
	parsed, err := ParseWithContext(ctx, raw, DefaultParseOptions())
	if err != nil {
		return nil, err
	}
	instance, err := AdmitInstantiated(parsed)
	if err != nil {
		return nil, err
	}
	if verifyDigest {
		actual, digestErr := snapshotInstanceHash(instance, profile)
		if digestErr != nil {
			return nil, digestErr
		}
		if actual != expectedDigest {
			return nil, invalidScenario()
		}
	}
	return instance, nil
}

const legacyVulnerabilitiesField = "vulnerabilities"

func snapshotInstanceHash(instance InstantiatedScenario, profile string) (string, error) {
	if profile == instantiatedSnapshotProfile {
		return CanonicalDigest(instance)
	}
	raw, err := CanonicalBytes(instance)
	if err != nil {
		return "", err
	}
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}, ingress.Object)
	if err != nil {
		return "", err
	}
	snapshot := snapshotObject(value)
	snapshot["profile"] = profile
	return snapshotHash(snapshot)
}
