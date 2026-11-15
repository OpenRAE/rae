package admission

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type replacementHistory struct {
	owner          *Validator
	root           any
	plans          map[string]any
	entries        map[string]any
	entryPlans     map[string]any
	receipts       map[string][]any
	byVersion      map[[2]string]any
	byRun          map[string][]any
	chains         map[string][]any
	usedSuperseded map[string]bool
}

func (e *Validator) replacementStudyRuns(root any, children []validation.Value, runs []any, receipts []validation.Value) ([]any, error) {
	history := replacementHistory{owner: e, root: root, plans: map[string]any{}, entries: map[string]any{}, entryPlans: map[string]any{}, receipts: map[string][]any{}, byVersion: map[[2]string]any{}, byRun: map[string][]any{}, chains: map[string][]any{}, usedSuperseded: map[string]bool{}}
	if at(root, "replacement_origin") != nil || len(children) > len(object(at(root, "entries")))*countAt(root, "replacement_policy", "max_replacements") {
		return nil, invalid()
	}
	if err := history.indexPlans(children); err != nil {
		return nil, err
	}
	if err := history.indexReceipts(receipts); err != nil {
		return nil, err
	}
	if err := history.indexRuns(runs); err != nil {
		return nil, err
	}
	return history.analysisRuns()
}
func (h *replacementHistory) indexPlans(children []validation.Value) error {
	rootID := stringAt(h.root, fieldPlanID)
	h.plans[rootID] = h.root
	for _, value := range children {
		child, err := h.owner.experimentValue(value, trialPlanContract)
		if err != nil {
			return err
		}
		id := stringAt(child, fieldPlanID)
		origin := at(child, "replacement_origin")
		if h.plans[id] != nil || origin == nil {
			return invalid()
		}
		if !equal(at(origin, "root_plan_id"), at(h.root, fieldPlanID)) || !equal(at(origin, "root_plan_digest"), at(h.root, "plan_digest")) || at(h.root, "entries", stringAt(origin, "root_entry_id")) == nil {
			return invalid()
		}
		h.plans[id] = child
		slot := stringAt(origin, "root_entry_id")
		h.chains[slot] = append(h.chains[slot], child)
	}
	return h.indexEntryIdentities()
}
func (h *replacementHistory) indexEntryIdentities() error {
	runIDs := map[string]bool{}
	for _, plan := range h.plans {
		for id, entry := range object(at(plan, "entries")) {
			runID := stringAt(entry, termRunID)
			if h.entries[id] != nil || runIDs[runID] {
				return invalid()
			}
			h.entries[id] = entry
			h.entryPlans[id] = plan
			runIDs[runID] = true
		}
	}
	return nil
}
func (h *replacementHistory) indexReceipts(values []validation.Value) error {
	seenIDs, seenAttempts := map[string]bool{}, map[string]bool{}
	for _, value := range values {
		receipt, err := h.owner.experimentValue(value, termTrialCleanupReceiptV1)
		if err != nil {
			return err
		}
		if err = cleanupReceiptLocal(receipt); err != nil {
			return err
		}
		id, attempt, entryID := stringAt(receipt, "receipt_id"), stringAt(receipt, "execution_attempt_id"), stringAt(receipt, fieldPlanEntryID)
		if seenIDs[id] || seenAttempts[attempt] || h.entries[entryID] == nil {
			return invalid()
		}
		seenIDs[id], seenAttempts[attempt] = true, true
		cleanup := h.cleanup(entryID)
		if err = cleanupReceiptJoin(cleanup, receipt); err != nil {
			return err
		}
		h.receipts[entryID] = append(h.receipts[entryID], receipt)
		if len(h.receipts[entryID]) > countAt(cleanup, "retry_policy", termMaxAttempts) {
			return invalid()
		}
	}
	return nil
}
func (h *replacementHistory) cleanup(entryID string) any {
	return at(h.entryPlans[entryID], "cleanup_plans", stringAt(h.entries[entryID], "execution_controls", "cleanup_plan_ref"))
}
func (h *replacementHistory) indexRuns(runs []any) error {
	for _, run := range runs {
		key := [2]string{stringAt(run, termRunID), stringAt(run, "run_version")}
		if h.byVersion[key] != nil {
			return invalid()
		}
		linkage := at(run, "trial_provenance")
		plan := h.plans[stringAt(linkage, fieldPlanID)]
		if linkage == nil || plan == nil {
			return invalid()
		}
		entryID := stringAt(linkage, fieldPlanEntryID)
		receipts := h.receipts[entryID]
		if err := h.owner.trialRunJoin(plan, run, receipts); err != nil {
			return err
		}
		referenced := rowSet(at(linkage, "execution_attempts"), "cleanup_receipt_ref")
		retained := map[string]bool{}
		for _, receipt := range receipts {
			retained[stringAt(receipt, "receipt_id")] = true
		}
		if !equalSet(referenced, retained) {
			return invalid()
		}
		h.byVersion[key] = run
		h.byRun[key[0]] = append(h.byRun[key[0]], run)
	}
	return nil
}
func (h *replacementHistory) analysisRuns() ([]any, error) {
	result := []any{}
	for _, slot := range slices.Sorted(maps.Keys(object(at(h.root, "entries")))) {
		chain := h.chains[slot]
		slices.SortFunc(chain, func(a, b any) int {
			return countAt(a, "replacement_origin", "ordinal") - countAt(b, "replacement_origin", "ordinal")
		})
		leaf, err := h.follow(slot, chain)
		if err != nil {
			return nil, err
		}
		run, known, err := h.leafRun(leaf, chain)
		if err != nil {
			return nil, err
		}
		if known && replacementAnalysisEligible(run, at(h.root, "replacement_policy")) {
			result = append(result, run)
		}
	}
	for id, versions := range h.byRun {
		for _, run := range versions {
			if stringAt(run, "run_status") == statusSuperseded && !h.usedSuperseded[id] {
				return nil, invalid()
			}
		}
	}
	return result, nil
}
func (h *replacementHistory) leafRun(leaf any, chain []any) (any, bool, error) {
	versions := h.byRun[stringAt(leaf, termRunID)]
	if len(versions) > 1 || len(chain) > 0 && len(versions) > 0 && stringAt(versions[0], "run_version") != "1" {
		return nil, false, invalid()
	}
	if len(versions) == 0 {
		return nil, false, nil
	}
	return versions[0], true, nil
}

func replacementAnalysisEligible(run, policy any) bool {
	return run != nil && analysisEligible(run) && (countAt(policy, "max_replacements") <= 0 || !set(at(policy, "replace_on"))[stringAt(run, "run_status")])
}
func (h *replacementHistory) follow(slot string, chain []any) (any, error) {
	parent, leaf := h.root, at(h.root, "entries", slot)
	for index, child := range chain {
		origin := at(child, "replacement_origin")
		if countAt(origin, "ordinal") != index+1 || !equal(at(origin, "parent_plan_id"), at(parent, fieldPlanID)) || !equal(at(origin, "parent_entry_id"), at(leaf, fieldPlanEntryID)) {
			return nil, invalid()
		}
		run, err := h.validateChild(slot, parent, child)
		if err != nil {
			return nil, err
		}
		superseded, err := h.expectedSupersession(run, child)
		if err != nil {
			return nil, err
		}
		if err = h.parentVersions(run, superseded); err != nil {
			return nil, err
		}
		h.usedSuperseded[stringAt(run, termRunID)] = true
		parent = child
		for _, entry := range object(at(child, "entries")) {
			leaf = entry
		}
	}
	return leaf, nil
}
func (h *replacementHistory) expectedSupersession(run, child any) (any, error) {
	raw, err := json.Marshal(run)
	if err != nil {
		return nil, invalid()
	}
	raw, err = h.owner.supersededRunProjection(raw, child)
	if err != nil {
		return nil, err
	}
	var expected any
	if decodeExact(raw, &expected) != nil {
		return nil, invalid()
	}
	retained := h.byVersion[[2]string{stringAt(expected, termRunID), stringAt(expected, "run_version")}]
	if retained == nil || !equal(expected, retained) {
		return nil, invalid()
	}
	return expected, nil
}

func (h *replacementHistory) parentVersions(run, superseded any) error {
	versions := h.byRun[stringAt(run, termRunID)]
	expected := map[string]bool{stringAt(run, "run_version"): true, stringAt(superseded, "run_version"): true}
	if len(versions) != len(expected) {
		return invalid()
	}
	for _, version := range versions {
		if !expected[stringAt(version, "run_version")] {
			return invalid()
		}
	}
	return nil
}
