package experiment

import (
	"context"
	"encoding/json"
	"fmt"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func (c *coordinator) Records(ctx context.Context, id Identity, options RecordOptions) (RecordBundle, error) {
	if err := c.authorize(ctx, id); err != nil {
		return RecordBundle{}, err
	}
	release, err := c.acquire(ctx)
	if err != nil {
		return RecordBundle{}, err
	}
	defer release()
	records, err := c.load(ctx)
	if err != nil {
		return RecordBundle{}, err
	}
	if err = c.restoreChildren(ctx, records); err != nil {
		return RecordBundle{}, err
	}
	collection, err := newRecordCollection(c, options, records)
	if err != nil {
		return RecordBundle{}, err
	}
	for _, slot := range c.slotSnapshot() {
		if err = collection.slot(ctx, slot); err != nil {
			return collection.bundle, err
		}
	}
	bundle := collection.bundle
	started := collection.started
	if err = validateRecordMetadata(options, started); err != nil {
		return bundle, err
	}
	bundle.Accounting = summarizeRecords(len(c.slotSnapshot()), bundle)
	if options.Study != nil {
		if err = c.assembleStudy(ctx, &bundle, *options.Study, options.Evidence, records); err != nil {
			return bundle, err
		}
	}
	if options.Archive != nil {
		if err = c.publishRecords(ctx, bundle, options.Archive, records); err != nil {
			return bundle, err
		}
	}
	return bundle, nil
}

func validateRecordMetadata(options RecordOptions, started map[string]bool) error {
	for key := range options.Metadata {
		if !started[key] {
			return invalidOptions()
		}
	}
	return nil
}

type recordCollection struct {
	coordinator *coordinator
	options     RecordOptions
	records     []Decision
	bundle      RecordBundle
	versions    map[string]any
	originals   map[string]scientificOriginal
	started     map[string]bool
}

func newRecordCollection(c *coordinator, options RecordOptions, records []Decision) (*recordCollection, error) {
	bundle := RecordBundle{Runs: []binding.ExperimentRunV1{}, Sources: []RecordSource{}, ValidationByRun: map[string]string{}, ValidationFailures: map[string][]string{}, EligibleRunIDs: []string{}, StudyValidation: termNotPerformed}
	versions, err := retainedVersions(records, c.id)
	if err != nil {
		return nil, err
	}
	for _, key := range slices.Sorted(maps.Keys(versions)) {
		if strings.HasPrefix(key, "run:") {
			var run binding.ExperimentRunV1
			if err = convert(versions[key], &run); err != nil {
				return nil, err
			}
			bundle.RetainedHistory = append(bundle.RetainedHistory, run)
		}
	}
	originals, err := canonicalArchivalRuns(records, c.id)
	if err != nil {
		return nil, err
	}
	return &recordCollection{coordinator: c, options: options, records: records, bundle: bundle, versions: versions, originals: originals, started: map[string]bool{}}, nil
}
func (r *recordCollection) slot(ctx context.Context, slot trialSlot) error {
	var err error

	attempts := slotAttempts(r.records, r.coordinator.id, slot.entry.PlanEntryID)
	if len(attempts) == 0 {
		return nil
	}
	r.started[slot.entry.RunID] = true
	source, sourceErr := r.coordinator.recordSource(ctx, slot, r.records, attempts)
	if sourceErr != nil {
		return sourceErr
	}
	run, assembleErr := assembleRun(source, r.options.Metadata[slot.entry.RunID], r.coordinator.options.Inputs.Task)
	if assembleErr != nil {
		return assembleErr
	}
	run, checked, linkErr := accountingValidationRecord(run, r.originals)
	if linkErr != nil {
		return linkErr
	}
	view, viewErr := transportView(run)
	if viewErr != nil {
		return viewErr
	}
	if err = retainVersion(r.versions, termRun, view); err != nil {
		return err
	}
	if err = validateRunAccounting(source, run); err != nil {
		return err
	}
	status := termPassed
	if checkErr := r.coordinator.validateRun(ctx, source, checked, r.options.Evidence); checkErr != nil {
		status = termFailed
		r.bundle.ValidationFailures[slot.entry.RunID] = []string{"task-evidence-validation-failed"}
	}
	r.bundle.ValidationByRun[slot.entry.RunID] = status
	r.bundle.Runs = append(r.bundle.Runs, run)
	r.bundle.ValidationRecords = append(r.bundle.ValidationRecords, checked)
	r.bundle.Sources = append(r.bundle.Sources, source)
	checkedView, checkedErr := transportView(checked)
	if checkedErr != nil {
		return checkedErr
	}
	if status == termPassed && analysisEligible(checkedView, slot.view, r.records, r.coordinator.id) {
		r.bundle.EligibleRunIDs = append(r.bundle.EligibleRunIDs, slot.entry.RunID)
	}
	return nil
}
func validateRunAccounting(source RecordSource, run binding.ExperimentRunV1) error {
	planValue, planErr := planAdmission(source.Plan)
	if planErr != nil {
		return planErr
	}
	owner, ownerErr := experimentOwner()
	if ownerErr != nil {
		return ownerErr
	}
	runRaw, encodeErr := json.Marshal(run)
	if encodeErr != nil {
		return encodeErr
	}
	receipts := sourceReceipts(source)
	return admission.ValidateTrialRunJSON(owner, planValue, runRaw, receipts)
}
func (c *coordinator) recordSource(ctx context.Context, s trialSlot, records []Decision, attempts []map[string]any) (RecordSource, error) {
	t := s.request(attempts[len(attempts)-1])
	t.Identity = c.options.Identity
	source, err := ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (RecordSource, error) { return c.options.Host.Records(work, copyTrial(t)) })
	if err != nil {
		return source, err
	}
	// Host facts cannot replace experiment starts, identity, admitted plans or observations.
	source.RunID, source.Plan, source.Realization = s.entry.RunID, s.plan, s.realization
	ids := retainSourceDecisions(&source, records, attempts)
	source.OperationRefs = maps.Clone(source.OperationRefs)
	for key, refs := range source.OperationRefs {
		if !ids[key] {
			return source, integrity()
		}
		source.OperationRefs[key] = slices.Clone(refs)
	}
	source.PhaseStates = maps.Clone(source.PhaseStates)
	source.OperationStates = maps.Clone(source.OperationStates)
	source.ExecutionSnapshots = maps.Clone(source.ExecutionSnapshots)
	source.OperationReceipts, err = copyDTO(source.OperationReceipts)
	if err != nil {
		return source, err
	}
	if err = retainExecutionSnapshots(&source); err != nil {
		return source, err
	}
	return detachSource(source)
}
func retainSourceDecisions(source *RecordSource, records []Decision, attempts []map[string]any) map[string]bool {
	source.Attempts = []Decision{}
	source.Observations = []Decision{}
	ids := map[string]bool{}
	for _, a := range attempts {
		ids[text(a, termExecutionAttemptID)] = true
	}
	for _, record := range records {
		m := decisionMap(record)
		if ids[text(m, termExecutionAttemptID)] {
			if record.SchemaVersion() == attemptSchema {
				source.Attempts = append(source.Attempts, record)
			}
			if record.SchemaVersion() == observationSchema {
				source.Observations = append(source.Observations, record)
			}
		}
	}
	slices.SortFunc(source.Attempts, func(a, b Decision) int {
		return integer(decisionMap(a)["attempt"]) - integer(decisionMap(b)["attempt"])
	})
	slices.SortFunc(source.Observations, func(a, b Decision) int {
		am, bm := decisionMap(a), decisionMap(b)
		if n := strings.Compare(text(am, termExecutionAttemptID), text(bm, termExecutionAttemptID)); n != 0 {
			return n
		}
		return strings.Compare(text(am, "observation", "kind"), text(bm, "observation", "kind"))
	})
	return ids
}
func retainExecutionSnapshots(source *RecordSource) error {
	for _, record := range source.Observations {
		m := decisionMap(record)
		if text(m, "observation", "kind") == termExecution && m["snapshot_json"] != nil {
			var snapshot binding.RuntimeSnapshotV1
			if json.Unmarshal([]byte(text(m, "snapshot_json")), &snapshot) != nil {
				return integrity()
			}
			if source.ExecutionSnapshots == nil {
				source.ExecutionSnapshots = map[string]binding.RuntimeSnapshotV1{}
			}
			source.ExecutionSnapshots[text(m, termExecutionAttemptID)] = snapshot
		}
	}
	return nil
}
func convert(v, target any) error {
	raw, err := json.Marshal(v)
	if err != nil || json.Unmarshal(raw, target) != nil {
		return integrity()
	}
	return nil
}
func assembleRun(source RecordSource, metadata RunMetadata, task binding.ExperimentTaskV1) (binding.ExperimentRunV1, error) {
	var result binding.ExperimentRunV1
	payload, err := assembleRunPayload(source, metadata, task)
	if err != nil {
		return result, err
	}
	owner, err := experimentOwner()
	if err != nil {
		return result, err
	}
	if err = checkRecordTree(payload); err != nil {
		return result, err
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return result, err
	}
	raw, err = admission.ExperimentModelProjection(owner, "experiment-run-v1", raw)
	if err != nil {
		return result, err
	}
	err = json.Unmarshal(raw, &result)
	return result, err
}
func assembleRunPayload(source RecordSource, metadata RunMetadata, task binding.ExperimentTaskV1) (map[string]any, error) {
	var result map[string]any
	if len(source.Attempts) == 0 {
		return result, integrity()
	}
	plan, err := transportView(source.Plan)
	if err != nil {
		return result, err
	}
	entryID := text(decisionMap(source.Attempts[0]), termPlanEntryID)
	entry := at(plan, "entries", entryID)
	attempts := []any{}
	for _, a := range source.Attempts {
		attempt, attemptErr := assembleAttempt(source, decisionMap(a))
		if attemptErr != nil {
			return result, attemptErr
		}
		attempts = append(attempts, attempt)
	}
	latest := attempts[len(attempts)-1]
	metadata, err = completeMetadata(metadata, task)
	if err != nil {
		return result, err
	}
	traceability, err := recordTraceability(source, metadata, plan)
	if err != nil {
		return result, err
	}
	payload := map[string]any{"schema_version": "experiment-run/v1", "record_state": "partial", termRunID: source.RunID, "run_version": metadata.RunVersion, "task_ref": at(plan, "input_refs", "task_ref"), "scenario_snapshot_ref": map[string]any{termRefKind: "scenario-snapshot", termRefID: at(plan, "input_refs", "scenario_family_ref", termRefID), termRefVersion: "raes-sdl-instantiated-snapshot/v2", termRefDigest: source.Realization.SnapshotDigest}, "stochastic_controls": mapValues(object(plan["stochastic_controls"])), "stochastic_draws": listOrEmpty(at(entry, "stochastic_draws")), termStartedAt: at(attempts[0], termStartedAt), "ended_at": at(latest, "ended_at"), "clock_context": map[string]any{"clock_id": "runtime-utc", "authority": "runtime UTC clock", "time_domain": "wall-clock", "synchronization": "Clock synchronization is not attested by record production."}, "run_status": runStatus(text(latest, "execution_status")), "outcome_status": metadata.OutcomeStatus, "traceability": traceability, "realized_selections": realizedSelections(entry), "realized_bindings": realizedBindings(entry, latest), "apparatus_context": metadata.ApparatusContext, "participant_implementation_provenance": rawOrNil(metadata.ParticipantImplementationProvenance), "invalidation": rawOrNil(metadata.Invalidation), "parameter_set": nonNilRaw(metadata.ParameterSet), "evidence_artifacts": nonNilRaw(metadata.EvidenceArtifacts), "result_summaries": metadata.ResultSummaries, "realized_form_disclosures": nonNilRaw(metadata.RealizedFormDisclosures), "execution_accounting": map[string]any{termPlanID: plan[termPlanID], termPlanDigest: plan[termPlanDigest], termPlanEntryID: entryID, "entry_digest": at(entry, "entry_digest"), "attempts": attempts, "participant_configurations": listOrEmpty(at(entry, "participant_configurations"))}}
	if err = mergeRecordBindings(payload, metadata.RealizedBindings); err != nil {
		return result, err
	}
	full := completeArchivalRecord(metadata, entry, traceability, latest, attempts)
	if len(metadata.Invalidation) > 0 {
		payload["run_status"] = "invalidated"
	}
	if full {
		payload["record_state"] = "archival"
		payload["trial_provenance"] = trialProvenance(source, plan, entry, attempts)
	} else {
		raw, hashErr := canonical(payload)
		if hashErr != nil {
			return result, hashErr
		}
		payload["run_version"] = "partial-" + strings.TrimPrefix(digest.SHA256(raw), "sha256:")
	}
	return payload, nil
}

func mergeRecordBindings(payload map[string]any, bindings []json.RawMessage) error {
	automatic := map[string]bool{}
	for _, binding := range array(payload["realized_bindings"]) {
		automatic[text(binding, "descriptor", "binding_id")] = true
	}
	for _, raw := range bindings {
		var b any
		if json.Unmarshal(raw, &b) != nil || automatic[text(b, "descriptor", "binding_id")] {
			return integrity()
		}
		payload["realized_bindings"] = append(array(payload["realized_bindings"]), b)
	}
	return nil
}
func completeArchivalRecord(metadata RunMetadata, entry, traceability, latest any, attempts []any) bool {
	full := at(latest, "ended_at") != nil && metadata.ApparatusContext != nil && traceability != nil && len(metadata.EvidenceArtifacts) > 0 && len(metadata.ResultSummaries) > 0 && (len(metadata.ParticipantImplementationProvenance) > 0 || len(array(at(entry, "participant_configurations"))) == 0)
	for _, attempt := range attempts {
		full = full && at(attempt, "cleanup_receipt") != nil
	}
	return full
}
func mapValues(m map[string]any) []any {
	values := make([]any, 0, len(m))
	for _, key := range slices.Sorted(maps.Keys(m)) {
		values = append(values, m[key])
	}
	return values
}
func rawOrNil(raw json.RawMessage) any {
	if len(raw) == 0 {
		return nil
	}
	return raw
}
func nonNilRaw(raw []json.RawMessage) []json.RawMessage {
	if raw == nil {
		return []json.RawMessage{}
	}
	return raw
}
func runStatus(state string) string {
	return map[string]string{termSucceeded: termCompleted, termFailed: termFailed, termCancelled: termAborted, termTimedOut: termFailed, termAborted: termAborted, termRunning: "in-progress", termUnknown: termIndeterminate}[state]
}
func completeMetadata(metadata RunMetadata, task binding.ExperimentTaskV1) (RunMetadata, error) {
	if metadata.RunVersion == "" {
		metadata.RunVersion = "1"
	}
	if metadata.OutcomeStatus == "" {
		metadata.OutcomeStatus = "not-evaluated"
	}
	metadata.ResultSummaries = maps.Clone(metadata.ResultSummaries)
	if metadata.ResultSummaries == nil {
		metadata.ResultSummaries = map[string]json.RawMessage{}
	}
	return completeMetrics(metadata, task)
}
func completeMetrics(metadata RunMetadata, task binding.ExperimentTaskV1) (RunMetadata, error) {
	taskView, err := transportView(task)
	if err != nil {
		return metadata, err
	}
	declared := map[string]bool{}
	for _, metric := range object(at(taskView, "evaluation_protocol", "metric_definitions")) {
		declared[text(metric, "metric_id")] = true
	}
	reported := map[string]bool{}
	for _, raw := range metadata.ResultSummaries {
		var result any
		if json.Unmarshal(raw, &result) != nil || !declared[text(result, "metric_id")] {
			return metadata, integrity()
		}
		reported[text(result, "metric_id")] = true
	}
	for _, metric := range slices.Sorted(maps.Keys(declared)) {
		if reported[metric] {
			continue
		}
		base := "missing:" + metric
		key := base
		for suffix := 1; metadata.ResultSummaries[key] != nil; suffix++ {
			key = fmt.Sprintf("%s:%d", base, suffix)
		}
		raw, encodeErr := json.Marshal(map[string]any{"metric_id": metric, "value_status": "missing", "notes": "No measured result was supplied.", "value": nil, "uncertainty": nil, "evidence_refs": []any{}})
		if encodeErr != nil {
			return metadata, encodeErr
		}
		metadata.ResultSummaries[key] = raw
	}
	return metadata, nil
}

func assembleAttempt(source RecordSource, attempt map[string]any) (map[string]any, error) {
	id := text(attempt, termExecutionAttemptID)
	observed := attemptObservations(source.Observations, id)
	evidence, err := observedEvidence(source.Observations, id)
	if err != nil {
		return nil, err
	}
	refs := []any{}
	records := []any{}
	for _, record := range evidence {
		refs = append(refs, map[string]any{termRefKind: "evidence-record", termRefID: at(record, "evidence_record_id"), termRefVersion: at(record, "record_version")})
		records = append(records, record)
	}
	execution, ended := attemptExecution(observed)
	configuration := attemptConfiguration(source, id, observed)
	capture := attemptCapture(source, id, observed)
	cleanupStatus, receipt := attemptCleanup(source, id, observed)
	operations := slices.Clone(source.OperationRefs[id])
	if operations == nil {
		operations = []string{}
	}
	slices.Sort(operations)
	if len(records) > 1024 {
		records = []any{}
	}
	return map[string]any{termExecutionAttemptID: id, "attempt": attempt["attempt"], termStartedAt: attempt[termStartedAt], "ended_at": ended, "execution_status": execution, "configuration_status": configuration, termCaptureStatus: capture, "cleanup_status": cleanupStatus, "cleanup_receipt": receipt, termOperationRefs: operations, "evidence_record_refs": refs, "evidence_records": records}, nil
}
func attemptExecution(observed map[string]map[string]any) (string, any) {
	var ended any
	execution := termUnknown
	if observed[termExecution] != nil {
		execution = text(observed[termExecution], "observation", "state")
		for _, observation := range observed {
			if text(observation, "observed_at") > fmt.Sprint(ended) || ended == nil {
				if observation["observed_at"] != nil {
					ended = observation["observed_at"]
				}
			}
		}
	}
	return execution, ended
}
func attemptConfiguration(source RecordSource, id string, observed map[string]map[string]any) string {
	configuration := termUnobserved
	if observed[termConfiguration] != nil {
		configuration = "observed"
	} else if source.PhaseStates[id+":0"] == termFailed {
		configuration = termFailed
	}
	return configuration
}
func attemptCapture(source RecordSource, id string, observed map[string]map[string]any) string {
	capture := termUnobserved
	if o := observed[termCapture]; o != nil {
		capture = "partial"
		if truth(at(o, "observation", "complete")) {
			capture = "complete"
		}
	}
	if slices.Contains([]string{termFailed, termCancelled}, source.PhaseStates[id+":1"]) {
		capture = termFailed
	}
	return capture
}
func attemptCleanup(source RecordSource, id string, observed map[string]map[string]any) (string, any) {
	cleanupStatus := termUnobserved
	var receipt any
	if o := observed[termCleanup]; o != nil {
		receipt = at(o, "observation", "receipt")
		cleanupStatus = text(receipt, "cleanup_status")
	} else {
		for phase, state := range source.PhaseStates {
			if strings.HasPrefix(phase, id+":destroy:") && slices.Contains([]string{termFailed, termCancelled}, state) {
				cleanupStatus = termFailed
			}
		}
	}
	return cleanupStatus, receipt
}
func observedEvidence(observations []Decision, attempt string) ([]any, error) {
	result := []any{}
	seen := map[string]any{}
	for _, record := range observations {
		m := decisionMap(record)
		if attempt != "" && text(m, termExecutionAttemptID) != attempt {
			continue
		}
		for _, evidence := range array(at(m, "observation", termEvidence)) {
			key := text(evidence, "evidence_record_id") + ":" + text(evidence, "record_version")
			if prior, ok := seen[key]; ok {
				if !same(prior, evidence) {
					return nil, integrity()
				}
				continue
			}
			seen[key] = evidence
			result = append(result, evidence)
		}
	}
	return result, nil
}
func recordTraceability(source RecordSource, metadata RunMetadata, plan map[string]any) (any, error) {
	evidence, err := observedEvidence(source.Observations, "")
	if err != nil {
		return nil, err
	}
	var result any
	if len(evidence) > 0 && len(array(at(plan, "input_refs", "capture_spec_refs"))) > 0 {
		captureRefs := []any{}
		for _, ref := range array(at(plan, "input_refs", "capture_spec_refs")) {
			captureRefs = append(captureRefs, map[string]any{termRefKind: "capture-spec", termRefID: at(ref, termRefID), termRefVersion: at(ref, termRefVersion)})
		}
		evidenceRefs := []any{}
		for _, e := range evidence {
			evidenceRefs = append(evidenceRefs, map[string]any{termRefKind: "evidence-record", termRefID: at(e, "evidence_record_id"), termRefVersion: at(e, "record_version")})
		}
		result = map[string]any{"capture_spec_refs": captureRefs, "evidence_record_refs": evidenceRefs, "claim_refs": []any{}, "derived_measure_refs": []any{}, "notes": []any{}}
	}
	if len(metadata.Traceability) > 0 {
		if json.Unmarshal(metadata.Traceability, &result) != nil {
			return nil, integrity()
		}
		if !traceabilityEvidence(result, evidence) {
			return nil, integrity()
		}
	}
	return result, nil
}
func traceabilityEvidence(traceability any, evidence []any) bool {
	known := map[[2]string]bool{}
	for _, record := range evidence {
		known[[2]string{text(record, "evidence_record_id"), text(record, "record_version")}] = true
	}
	for _, ref := range array(at(traceability, "evidence_record_refs")) {
		if !known[[2]string{text(ref, termRefID), text(ref, termRefVersion)}] {
			return false
		}
	}
	return true
}
func realizedSelections(entry any) []any {
	result := []any{}
	for _, selection := range array(at(entry, "selections")) {
		if t := at(selection, "treatment"); t != nil {
			result = append(result, t)
		}
	}
	return result
}
func realizedBindings(entry, latest any) []any {
	configurations := map[string]string{}
	for _, c := range array(at(entry, "participant_configurations")) {
		configurations[text(c, "participant_address")] = text(c, "configuration_digest")
	}
	result := []any{}
	for _, b := range array(at(entry, "bindings")) {
		target := at(b, "descriptor", "target")
		var configDigest any
		switch text(target, "plane") {
		case "scenario":
		case "participant-implementation":
			if text(latest, "configuration_status") != "observed" {
				continue
			}
			configDigest = configurations[text(target, "participant_address")]
		default:
			continue
		}
		result = append(result, map[string]any{"descriptor": at(b, "descriptor"), "origin": at(b, "origin"), "configuration_digest": configDigest})
	}
	return result
}
func trialProvenance(source RecordSource, plan map[string]any, entry any, attempts []any) any {
	refs := []any{}
	for _, ref := range source.Realization.ProcessorPlanRefs {
		refs = append(refs, ref.Document())
	}
	execution := []any{}
	for _, attempt := range attempts {
		execution = append(execution, map[string]any{termExecutionAttemptID: at(attempt, termExecutionAttemptID), "cleanup_receipt_ref": at(attempt, "cleanup_receipt", "receipt_id"), termOperationRefs: at(attempt, termOperationRefs)})
	}
	return map[string]any{termPlanID: plan[termPlanID], termPlanDigest: plan[termPlanDigest], termPlanEntryID: at(entry, termPlanEntryID), "entry_digest": at(entry, "entry_digest"), "admitted_run_id": at(entry, termRunID), "coordinate": at(entry, "coordinate"), "instantiated_scenario_digest": source.Realization.SnapshotDigest, "processor_plan_refs": refs, "execution_attempts": execution, "terminal_attempt_id": at(attempts[len(attempts)-1], termExecutionAttemptID)}
}
func sourceReceipts(source RecordSource) [][]byte {
	receipts := [][]byte{}
	for _, record := range source.Observations {
		m := decisionMap(record)
		if text(m, "observation", "kind") == termCleanup {
			raw, err := json.Marshal(at(m, "observation", "receipt"))
			if err == nil {
				receipts = append(receipts, raw)
			}
		}
	}
	return receipts
}
func analysisEligible(run, plan any, records []Decision, id string) bool {
	if !archivalRun(run) || slices.Contains([]string{"invalidated", "superseded"}, text(run, "run_status")) || text(run, "outcome_status") == "not-evaluated" {
		return false
	}
	if integer(at(plan, "replacement_policy", "max_replacements")) > 0 && slices.Contains(array(at(plan, "replacement_policy", "replace_on")), any(text(run, "run_status"))) {
		return false
	}
	for _, record := range records {
		if record.SchemaVersion() == replacementSchema {
			m := decisionMap(record)
			if text(m, termExperimentID) == id && text(m, "parent_run", termRunID) == text(run, termRunID) {
				return false
			}
		}
	}
	return true
}
func summarizeRecords(planned int, bundle RecordBundle) Accounting {
	a := Accounting{PlannedRuns: planned, StartedRuns: len(bundle.Runs), UnstartedRuns: planned - len(bundle.Runs), RunOutcomes: map[string]int{}, ScientificOutcomes: map[string]int{}, ExecutionOutcomes: map[string]int{}, CaptureOutcomes: map[string]int{}, CleanupOutcomes: map[string]int{}, ValidationOutcomes: map[string]int{}, MetricPopulations: map[string]map[string]int{}}
	for index, run := range bundle.Runs {
		view, _ := transportView(run)
		a.RunOutcomes[text(view, "run_status")]++
		a.ScientificOutcomes[text(view, "outcome_status")]++
		a.ValidationOutcomes[bundle.ValidationByRun[text(view, termRunID)]]++
		attempts := array(at(view, "execution_accounting", "attempts"))
		a.Attempts += len(attempts)
		for _, attempt := range attempts {
			a.ExecutionOutcomes[text(attempt, "execution_status")]++
			a.CaptureOutcomes[text(attempt, termCaptureStatus)]++
			a.CleanupOutcomes[text(attempt, "cleanup_status")]++
		}
		if len(attempts) > 0 && slices.Contains([]string{termUnknown, termRunning}, text(attempts[len(attempts)-1], "execution_status")) {
			a.UnresolvedRuns++
		}
		plan, _ := transportView(bundle.Sources[index].Plan)
		if plan["replacement_origin"] != nil {
			a.ReplacementRuns++
		}
		summarizeMetrics(&a, view, slices.Contains(bundle.EligibleRunIDs, text(view, termRunID)))
	}
	a.ResolvedRuns = a.StartedRuns - a.UnresolvedRuns
	a.RetryAttempts = a.Attempts - a.StartedRuns
	return a
}
func summarizeMetrics(a *Accounting, run any, eligible bool) {
	byMetric := map[string][]any{}
	for _, result := range object(at(run, "result_summaries")) {
		key := text(result, "metric_id")
		byMetric[key] = append(byMetric[key], result)
	}
	for key, results := range byMetric {
		summarizeMetricPopulation(a, key, results, eligible)
	}
}

func summarizeMetricPopulation(a *Accounting, key string, results []any, eligible bool) {
	m := a.MetricPopulations[key]
	if m == nil {
		m = map[string]int{}
		a.MetricPopulations[key] = m
	}
	m["started_runs"]++
	if eligible {
		m["eligible_runs"]++
	}
	reported, missing, withheld := false, true, false
	for _, result := range results {
		state := text(result, "value_status")
		if state == "reported" {
			m["reported_results"]++
			reported = true
		}
		missing = missing && state == "missing"
		withheld = withheld || state == "withheld"
	}
	if reported {
		m["reported_runs"]++
	}
	if missing {
		m["missing_runs"]++
	}
	if withheld {
		m["withheld_runs"]++
	}
}
func listOrEmpty(v any) []any {
	a := array(v)
	if a == nil {
		return []any{}
	}
	return a
}

func detachSource(source RecordSource) (RecordSource, error) {
	t := copyTrial(Trial{Plan: source.Plan, Realization: source.Realization})
	source.Plan = t.Plan
	source.Realization = t.Realization
	source.Attempts = slices.Clone(source.Attempts)
	source.Observations = slices.Clone(source.Observations)
	source.PhaseStates = maps.Clone(source.PhaseStates)
	source.OperationStates = maps.Clone(source.OperationStates)
	source.OperationRefs = maps.Clone(source.OperationRefs)
	for key, refs := range source.OperationRefs {
		source.OperationRefs[key] = slices.Clone(refs)
	}
	source.ExecutionSnapshots = maps.Clone(source.ExecutionSnapshots)
	for key, snapshot := range source.ExecutionSnapshots {
		copySnapshot, err := copyDTO(snapshot)
		if err != nil {
			return source, err
		}
		source.ExecutionSnapshots[key] = copySnapshot
	}
	var err error
	source.OperationReceipts, err = copyDTO(source.OperationReceipts)
	return source, err
}

func archivalRun(run any) bool {
	state := text(run, "record_state")
	return state == "" || state == "archival"
}
