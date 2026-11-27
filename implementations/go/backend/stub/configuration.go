package stub

import (
	"context"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/backend"
	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// Configuration supplies explicit constructor inputs. Only provisioning uses
// Envelope; the other doubles use Clock. Nil inputs preserve default behavior.
type Configuration struct {
	Clock    clock.Clock
	Envelope *binding.RealizationEnvelopeV1
}

// Provisioner exposes the portable provisioning double.
type Provisioner interface{ backend.Provisioner }

// Orchestrator exposes the portable orchestration double.
type Orchestrator interface{ backend.Orchestrator }

// Evaluator exposes the portable evaluation double.
type Evaluator interface{ backend.Evaluator }

// ParticipantRuntime exposes the portable participant lifecycle double.
type ParticipantRuntime interface{ backend.ParticipantRuntime }

func callReady(ctx context.Context) error {
	if ctx == nil {
		return invalid()
	}
	return ctx.Err()
}
func transportObject(input any) (map[string]any, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	if admission.CheckTransport(input, limits) != nil {
		return nil, invalid()
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, invalid()
	}
	decoded, err := ingress.Parse(raw, limits, ingress.Object)
	if err != nil {
		return nil, invalid()
	}
	result, ok := decoded.(map[string]any)
	if !ok {
		return nil, invalid()
	}
	return result, nil
}
func checkedPlan(input any, contract string) (map[string]any, error) {
	result, err := transportObject(input)
	if err != nil {
		return nil, err
	}
	owner, err := schemas()
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(result)
	if err != nil || owner.CheckPortable(contract, raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalid()
	}
	return result, nil
}
func snapshotObject(input binding.RuntimeSnapshotV1) (map[string]any, error) {
	if admission.CheckPreparedSnapshot(input) != nil {
		return nil, invalid()
	}
	result, err := transportObject(input)
	if err != nil {
		return nil, err
	}
	if _, present := result["entries"]; !present {
		result["entries"] = map[string]any{}
	}
	result[termSchemaVersion] = "runtime-snapshot/v1"
	return result, nil
}
func snapshotResult(input map[string]any) (binding.RuntimeSnapshotV1, error) {
	if admission.CheckTransportTree(input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return binding.RuntimeSnapshotV1{}, invalid()
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return binding.RuntimeSnapshotV1{}, invalid()
	}
	var result binding.RuntimeSnapshotV1
	if json.Unmarshal(raw, &result) != nil || admission.CheckPreparedSnapshot(result) != nil {
		return binding.RuntimeSnapshotV1{}, invalid()
	}
	return result, nil
}
func table(input map[string]any, key string) map[string]any {
	result := object(input, key)
	if result == nil {
		result = map[string]any{}
		input[key] = result
	}
	return result
}
func array(input any) []any                        { result, _ := input.([]any); return result }
func text(input map[string]any, key string) string { result, _ := input[key].(string); return result }
