package admission

import (
	"crypto/sha1" //nolint:gosec // UUIDv5 requires SHA-1 for stable identity; it supplies no security claim.
	"encoding/hex"
	"encoding/json"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

const (
	termAssignedTrialV1 = "assigned-trial-v1"
	// maxTrialParallelism is the published upper bound of an authored trial_parallelism count.
	maxTrialParallelism = 4096
)

// TrialAttemptID returns the original allocation identity of one trial attempt:
// a UUIDv5 in the URL namespace over the experiment, entry and attempt ordinal.
func TrialAttemptID(experimentID, entryID string, ordinal int) string {
	namespace := [16]byte{0x6b, 0xa7, 0xb8, 0x11, 0x9d, 0xad, 0x11, 0xd1, 0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8}
	hash := sha1.New() //nolint:gosec // UUIDv5 requires this published identity algorithm.
	_, _ = hash.Write(namespace[:])
	_, _ = hash.Write([]byte(experimentID + ":" + entryID + ":" + strconv.Itoa(ordinal)))
	sum := hash.Sum(nil)[:16]
	sum[6] = sum[6]&0x0f | 0x50
	sum[8] = sum[8]&0x3f | 0x80
	value := hex.EncodeToString(sum)
	return "attempt:" + value[:8] + "-" + value[8:12] + "-" + value[12:16] + "-" + value[16:20] + "-" + value[20:]
}

// assignedTrialLocal binds an assignment to its original plan: the entry, the
// allocated attempt identity, the admitted deadline, each processor commitment,
// a logical target and the admitted parallelism bounds.
func (e *Validator) assignedTrialLocal(root any) error {
	plan := object(at(root, "plan"))
	raw, err := json.Marshal(plan)
	if err != nil {
		return invalid()
	}
	if _, err = e.Validate(trialPlanContract, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil); err != nil {
		return err
	}
	entries := object(plan["entries"])
	entryID := stringAt(root, fieldPlanEntryID)
	entry := object(entries[entryID])
	if entry == nil {
		return invalid()
	}
	experimentID := stringAt(plan, "plan_id")
	if origin := object(plan["replacement_origin"]); origin != nil {
		experimentID = stringAt(origin, "root_plan_id")
	}
	attempt, _ := integer(at(root, "attempt"))
	if stringAt(root, "execution_attempt_id") != TrialAttemptID(experimentID, entryID, attempt) {
		return invalid()
	}
	if err = assignedDeadline(root, entry); err != nil {
		return err
	}
	kinds := []string{}
	for _, ref := range array(at(root, "processor_plan_refs")) {
		kinds = append(kinds, stringAt(ref, "plan_kind"))
	}
	slices.Sort(kinds)
	if !slices.Equal(slices.Compact(kinds), []string{"evaluation", "orchestration", "provisioning"}) || !strings.HasPrefix(stringAt(root, "target_scope"), "target:") {
		return invalid()
	}
	lower, upper, err := trialParallelismBounds(object(plan["trial_parallelism"]), len(entries))
	if err != nil {
		return err
	}
	effective := 1
	if value, present := object(root)["effective_parallelism"]; present {
		effective, _ = integer(value)
	}
	return require(lower <= effective && effective <= upper)
}

func assignedDeadline(root any, entry map[string]any) error {
	start, startErr := time.Parse(time.RFC3339Nano, stringAt(root, "started_at"))
	end, endErr := time.Parse(time.RFC3339Nano, stringAt(root, "deadline"))
	timeout, ok := integer(at(entry, "execution_controls", "attempt_timeout_seconds"))
	return require(startErr == nil && endErr == nil && ok && end.Sub(start).Seconds() == float64(timeout))
}

// trialParallelismBounds returns the inclusive parallel-trial bounds that the
// author sets; trials run one at a time without a value.
func trialParallelismBounds(intent map[string]any, entries int) (int, int, error) {
	if intent == nil {
		return 1, 1, nil
	}
	lower, upper := 1, min(entries, maxTrialParallelism)
	switch stringAt(intent, "posture") {
	case postureExact:
		count, _ := integer(intent["count"])
		lower, upper = count, count
	case "constrained":
		if minimum, ok := integer(intent["minimum"]); ok && minimum > 0 {
			lower = minimum
		}
		if maximum, ok := integer(intent["maximum"]); ok {
			upper = maximum
		}
	}
	if lower > upper {
		return 0, 0, invalid()
	}
	return lower, upper, nil
}

const (
	termAssignedTrialControlV1 = "assigned-trial-control-v1"
	termTrialOutcomeV1         = "trial-outcome-v1"
)

// trialHandoffLocal applies the portable value limits of every trial handoff,
// then the binding rules of its model.
func (e *Validator) trialHandoffLocal(id string, root any) error {
	if value.Validate(root, value.Runtime()) != nil {
		return invalid()
	}
	switch id {
	case termAssignedTrialV1:
		return e.assignedTrialLocal(root)
	case termTrialOutcomeV1:
		return trialOutcomeLocal(root)
	}
	return nil
}

// trialOutcomeLocal keeps the original observations: one fact of each kind, one
// record of each operation, and terminal execution and cleanup facts for a
// completed trial.
func trialOutcomeLocal(root any) error {
	kinds := []string{}
	for _, fact := range array(at(root, "facts")) {
		kind := stringAt(fact, "observation", "kind")
		if err := trialFact(fact, kind); err != nil {
			return err
		}
		kinds = append(kinds, kind)
	}
	operations := []string{}
	for _, operation := range array(at(root, "operations")) {
		receipt, status := at(operation, "receipt"), at(operation, "status")
		if stringAt(receipt, "operation_id") != stringAt(status, "operation_id") || !equal(at(receipt, "context"), at(status, "context")) {
			return invalid()
		}
		operations = append(operations, stringAt(receipt, "operation_id"))
	}
	completed := stringAt(root, "progress") != statusCompleted || slices.Contains(kinds, termExecution) && slices.Contains(kinds, "cleanup")
	return require(unique(kinds) && unique(operations) && completed)
}

func trialFact(fact any, kind string) error {
	snapshot := at(fact, "execution_snapshot")
	if (kind == termExecution) != (snapshot != nil) {
		return invalid()
	}
	if kind == termExecution && (!boolean(at(fact, "observation", "ceased")) || stringAt(fact, "observation", "state") == "running") {
		return invalid()
	}
	return nil
}
