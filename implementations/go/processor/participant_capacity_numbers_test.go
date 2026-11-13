package processor_test

import (
	"bytes"
	"encoding/json"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

//nolint:ireturn // Each use returns its requested concrete manifest transport type.
func capacityNumber[T any](t *testing.T, input T, number string, path ...string) T {
	t.Helper()
	raw := requireJSON(t, input)
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var record map[string]any
	if err := decoder.Decode(&record); err != nil {
		t.Fatal(err)
	}
	var parent any = record
	for _, key := range path[:len(path)-1] {
		if mapping, ok := parent.(map[string]any); ok {
			parent = mapping[key]
			continue
		}
		index, err := strconv.Atoi(key)
		if err != nil {
			t.Fatal(err)
		}
		parent = requireType[[]any](t, parent)[index]
	}
	requireType[map[string]any](t, parent)[path[len(path)-1]] = json.Number(number)
	var result T
	if err := json.Unmarshal(requireJSON(t, record), &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func autonomousCapacityManifest(t *testing.T) binding.BackendManifestV2 {
	t.Helper()
	raw, err := os.ReadFile("testdata/autonomous-support.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []struct {
		Manifest binding.BackendManifestV2 `json:"manifest"`
	}
	if err := json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	return vectors[0].Manifest
}

func checkedCapacitySupport(t *testing.T, model processor.RuntimeModel, manifest binding.BackendManifestV2, selected *binding.ProcessorManifestV2) processor.ParticipantSupportDiagnostics {
	t.Helper()
	defer func() {
		if recovered := recover(); recovered != nil {
			t.Fatalf("admitted integral capacity panicked: %v", recovered)
		}
	}()
	result, err := processor.ParticipantSupport(model, manifest, selected)
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func TestParticipantCapacityAcceptsIntegralJSONNumbers(t *testing.T) {
	model := autonomousSupportModels(t)["v1"]
	manifest := autonomousCapacityManifest(t)
	for _, number := range []string{"10", "10.0", "1e1", "9007199254740993", "9007199254740993.0", "9.007199254740993e15"} {
		t.Run("autonomous/"+number, func(t *testing.T) {
			target := capacityNumber(t, manifest, number, "capabilities", "participant_runtime", "max_autonomous_action_attempts")
			result := checkedCapacitySupport(t, model, target, nil)
			if gaps := autonomousTestMessages(result.Execution); len(gaps) != 0 {
				t.Fatalf("sufficient capacity refused: %v", gaps)
			}
		})
	}
	vectors := toolSupportVectors(t)
	toolModel := toolSupportModel(t, vectors.Sources["toolkit"])
	for _, field := range []string{"max_bindings_per_profile", "max_participants_per_binding"} {
		for _, number := range []string{"10", "10.0", "1e1"} {
			t.Run(field+"/"+number, func(t *testing.T) {
				target := capacityNumber(t, vectors.Backends["exact"], number, "capabilities", "participant_runtime", "tool_profiles", field)
				// Remove the other independent processor limit from this check.
				selected := capacityNumber(t, vectors.Processors["processor-capacity-independent"], "10", "capabilities", "participant_tools", "max_bindings_per_profile")
				selected = capacityNumber(t, selected, number, "capabilities", "participant_tools", field)
				result := checkedCapacitySupport(t, toolModel, target, &selected)
				if len(result.Tools) != 0 {
					t.Fatalf("sufficient capacity refused: %+v", result.Tools)
				}
			})
		}
	}
}

func TestParticipantResourcePoolAcceptsIntegralJSONNumbers(t *testing.T) {
	raw, err := os.ReadFile("testdata/participant-resource-profile.json")
	if err != nil {
		t.Fatal(err)
	}
	model := toolSupportModel(t, toolSupportSource{Text: string(raw)})
	raw, err = os.ReadFile("testdata/autonomous-v3-support.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []struct {
		Manifest binding.BackendManifestV2 `json:"manifest"`
	}
	if err := json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	for _, input := range []struct {
		field   string
		numbers []string
	}{
		{"capacity", []string{"1", "1.0", "1e0"}},
		{"protected_capacity", []string{"0", "0.0", "0e0"}},
		{"max_queue_ticks", []string{"20", "20.0", "2e1"}},
		{"starvation_bound_ticks", []string{"100", "100.0", "1e2"}},
	} {
		baseline := capacityNumber(t, vectors[0].Manifest, input.numbers[0], "capabilities", "participant_runtime", "resource_budgets", "configured_pools", "0", input.field)
		result := checkedCapacitySupport(t, model, baseline, nil)
		expected := autonomousTestMessages(result.Execution)
		if input.field == "capacity" && len(expected) == 0 {
			t.Fatal("insufficient resource capacity was accepted")
		}
		for _, number := range input.numbers {
			t.Run(input.field+"/"+number, func(t *testing.T) {
				target := capacityNumber(t, vectors[0].Manifest, number, "capabilities", "participant_runtime", "resource_budgets", "configured_pools", "0", input.field)
				result := checkedCapacitySupport(t, model, target, nil)
				gaps := autonomousTestMessages(result.Execution)
				if diff := cmp.Diff(expected, gaps); diff != "" {
					t.Fatalf("equivalent capacity changed diagnostics (-integer +equivalent):\n%s", diff)
				}
			})
		}
	}
}

func TestAutonomousCapacityKeepsEquivalentLimitDiagnostics(t *testing.T) {
	model := autonomousSupportModels(t)["v1"]
	manifest := autonomousCapacityManifest(t)
	baseline := capacityNumber(t, manifest, "1", "capabilities", "participant_runtime", "max_autonomous_action_attempts")
	result := checkedCapacitySupport(t, model, baseline, nil)
	expected := autonomousTestMessages(result.Execution)
	if !strings.Contains(strings.Join(expected, "\n"), "action attempts require 2, backend limit is 1") {
		t.Fatalf("lost exact threshold: %v", expected)
	}
	for _, number := range []string{"1", "1.0", "1e0"} {
		t.Run(number, func(t *testing.T) {
			target := capacityNumber(t, manifest, number, "capabilities", "participant_runtime", "max_autonomous_action_attempts")
			result := checkedCapacitySupport(t, model, target, nil)
			gaps := autonomousTestMessages(result.Execution)
			if diff := cmp.Diff(expected, gaps); diff != "" {
				t.Fatalf("equivalent capacity changed diagnostics (-integer +equivalent):\n%s", diff)
			}
		})
	}
}

func TestParticipantCapacityRetainsNumericInputBounds(t *testing.T) {
	model := autonomousSupportModels(t)["v1"]
	manifest := autonomousCapacityManifest(t)
	for _, number := range []string{"1e999999999", "0e999999999", "1e-999999999", strings.Repeat("1", 4301)} {
		t.Run(number[:min(24, len(number))], func(t *testing.T) {
			target := capacityNumber(t, manifest, number, "capabilities", "participant_runtime", "max_autonomous_action_attempts")
			result, err := processor.ParticipantSupport(model, target, nil)
			if err == nil || len(result.Tools)+len(result.Execution)+len(result.MixedControl) != 0 {
				t.Fatalf("out-of-budget capacity returned a result: error=%v", err)
			}
		})
	}
}
