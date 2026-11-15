package experiment

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

const (
	experimentSchema   = "runtime-experiment/v1"
	attemptSchema      = "runtime-trial-attempt/v1"
	observationSchema  = "runtime-trial-observation/v1"
	terminalSchema     = "runtime-trial-terminal/v1"
	cancelSchema       = "runtime-experiment-cancel/v1"
	replacementSchema  = "runtime-trial-replacement/v1"
	candidateSchema    = "runtime-trial-archive-candidate/v1"
	archiveSchema      = "runtime-trial-archive/v1"
	interruptionSchema = "runtime-trial-interruption/v1"
	studySchema        = "runtime-study-definition/v1"
	publicationSchema  = "runtime-record-publication/v1"
)

var experimentOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Compiled immutable contract owners; no caller records are cached.
func runtimeIngress() ingress.Limits                 { return ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64} }

type decision struct {
	id, schema string
	raw        []byte
}

func (d *decision) ID() string            { return d.id }
func (d *decision) SchemaVersion() string { return d.schema }
func (d *decision) JSON() []byte          { return bytes.Clone(d.raw) }
func (*decision) experimentDecision() {
	// Seals the public decision interface to this native owner.
}
func invalidDecision() error {
	return fault.New(fault.InvalidInput, "experiment-decision-invalid", nil)
}
func integrity() error { return fault.New(fault.EvidenceIntegrity, "experiment-evidence-invalid", nil) }

// DecodeDecision revalidates one bounded private runtime record and seals its identity.
func DecodeDecision(data []byte) (Decision, error) { //nolint:ireturn // Only this native owner can mint the sealed handle.
	parsed, err := ingress.Parse(data, runtimeIngress(), ingress.Object)
	if err != nil {
		return nil, invalidDecision()
	}
	document, ok := parsed.(map[string]any)
	if !ok {
		return nil, invalidDecision()
	}
	schema := text(document, "schema_version")
	identity, err := decisionIdentity(document, schema)
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return nil, invalidDecision()
	}
	idRaw, err := canonical(identity)
	if err != nil {
		return nil, err
	}
	return &decision{id: digest.SHA256(idRaw), schema: schema, raw: raw}, nil
}
func canonical(v any) ([]byte, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return nil, invalidDecision()
	}
	return canonjson.JCS(raw)
}
func same(a, b any) bool {
	ar, ae := canonical(a)
	br, be := canonical(b)
	return ae == nil && be == nil && bytes.Equal(ar, br)
}
func object(v any) map[string]any { m, _ := v.(map[string]any); return m }
func array(v any) []any           { a, _ := v.([]any); return a }
func text(v any, keys ...string) string {
	for _, key := range keys {
		v = object(v)[key]
	}
	s, _ := v.(string)
	return s
}
func at(v any, keys ...string) any {
	for _, key := range keys {
		v = object(v)[key]
	}
	return v
}
func integer(v any) int {
	n, ok := v.(json.Number)
	if !ok {
		return 0
	}
	i, err := n.Int64()
	if err != nil || i < 0 || i > int64(^uint(0)>>1) {
		return 0
	}
	return int(i)
}
func truth(v any) bool { b, _ := v.(bool); return b }
func identityString(v any) bool {
	s, ok := v.(string)
	return ok && utf8.RuneCountInString(s) > 0 && utf8.RuneCountInString(s) <= 256
}
func fields(m map[string]any, required, optional string) bool {
	r := strings.Fields(required)
	allowed := append(slices.Clone(r), strings.Fields(optional)...)
	for _, key := range r {
		if _, ok := m[key]; !ok {
			return false
		}
	}
	for key := range m {
		if !slices.Contains(allowed, key) {
			return false
		}
	}
	return true
}
func identities(v any, minCount, maxCount int) bool {
	a, ok := v.([]any)
	if !ok || len(a) < minCount || len(a) > maxCount {
		return false
	}
	for _, s := range a {
		if !identityString(s) {
			return false
		}
	}
	return true
}
func sha(v any) bool {
	s, ok := v.(string)
	return ok && len(s) == 71 && strings.HasPrefix(s, "sha256:") && strings.Trim(s[7:], "0123456789abcdef") == ""
}
func timestamp(v any) bool {
	s, ok := v.(string)
	if !ok {
		return false
	}
	_, err := time.Parse(time.RFC3339Nano, s)
	return err == nil
}
func localModel(id string, v any) error {
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	raw, err := json.Marshal(v)
	if err != nil {
		return invalidDecision()
	}
	if strings.HasPrefix(id, "experiment-") || id == "participant-configuration-result-v1" || id == "trial-cleanup-plan-v1" || id == contractTrialCleanupReceipt {
		projected, projectionErr := admission.ExperimentModelProjection(owner, id, raw)
		if projectionErr != nil {
			return projectionErr
		}
		parsed, parseErr := ingress.Parse(projected, runtimeIngress(), ingress.Object)
		if parseErr != nil {
			return parseErr
		}
		if target, valid := v.(map[string]any); valid {
			clear(target)
			maps.Copy(target, object(parsed))
		}
		return nil
	}
	return owner.CheckModelFragment(id, "#", raw, runtimeIngress())
}
func decisionIdentity(m map[string]any, schema string) ([]any, error) {
	if err := validateDecision(m, schema); err != nil {
		return nil, err
	}
	id := []any{schema}
	switch schema {
	case experimentSchema, cancelSchema, studySchema:
		id = append(id, m[termExperimentID])
	case attemptSchema:
		id = append(id, m[termExperimentID], m[termPlanEntryID], m["attempt"])
	case observationSchema:
		id = append(id, m[termExecutionAttemptID], at(m, "observation", "kind"))
	case terminalSchema, interruptionSchema:
		id = append(id, m[termExecutionAttemptID])
	case replacementSchema:
		id = append(id, m[termExperimentID], m["root_entry_id"], m["ordinal"])
	case candidateSchema, archiveSchema:
		id = append(id, m[termExperimentID], at(m, termRun, termRunID))
	case publicationSchema:
		kind, subject := termRun, m[termRun]
		if subject == nil {
			kind, subject = termStudy, m[termStudy]
		}
		id = append(id, m[termExperimentID], []any{kind, at(subject, kind+"_id"), at(subject, kind+"_version")}, m["validation_status"], m["failure_codes"], m["state"])
	default:
		return nil, invalidDecision()
	}
	return id, nil
}
func validateDecision(m map[string]any, schema string) error {
	if v, ok := m[termExperimentID]; ok && !identityString(v) {
		return invalidDecision()
	}
	if v, ok := m[termExecutionAttemptID]; ok && !identityString(v) {
		return invalidDecision()
	}
	switch schema {
	case experimentSchema:
		return validateAdmissionDecision(m)
	case attemptSchema:
		return validateAttemptDecision(m)
	case observationSchema:
		return validateObservationDecision(m)
	case terminalSchema:
		return validateTerminalDecision(m)
	case cancelSchema:
		if !fields(m, "schema_version experiment_id actor_id", "") || !identityString(m["actor_id"]) {
			return invalidDecision()
		}
	case interruptionSchema:
		if !fields(m, "schema_version execution_attempt_id cause disposition", "") || !slices.Contains([]string{termCancellation, "timeout"}, text(m, "cause")) || !slices.Contains([]string{"cancel", "abort", "cleanup-and-fail"}, text(m, "disposition")) {
			return invalidDecision()
		}
	case candidateSchema, archiveSchema, studySchema:
		field, id := termRun, contractExperimentRun
		if schema == studySchema {
			field, id = termStudy, contractExperimentStudy
		}
		if !fields(m, "schema_version experiment_id "+field, "") {
			return invalidDecision()
		}
		return localModel(id, m[field])
	case publicationSchema:
		return validatePublicationDecision(m)
	case replacementSchema:
		return validateReplacementDecision(m)
	default:
		return invalidDecision()
	}
	return nil
}
func validateAttemptDecision(m map[string]any) error {
	if !fields(m, "schema_version experiment_id plan_entry_id run_id attempt execution_attempt_id started_at deadline", "") || !identityString(m[termPlanEntryID]) || !identityString(m[termRunID]) || integer(m["attempt"]) < 1 || integer(m["attempt"]) > 1000 || !timestamp(m[termStartedAt]) || !timestamp(m["deadline"]) {
		return invalidDecision()
	}
	return nil
}
func validateTerminalDecision(m map[string]any) error {
	if !fields(m, "schema_version execution_attempt_id receipt capture_status reusable", "") || !slices.Contains([]string{termSucceeded, termFailed}, text(m, termCaptureStatus)) {
		return invalidDecision()
	}
	if _, ok := m["reusable"].(bool); !ok {
		return invalidDecision()
	}
	return localModel("batch-execution-receipt-v1", m["receipt"])
}
func validateAdmissionDecision(m map[string]any) error {
	if !fields(m, "schema_version experiment_id plan_digest realization_digests actor_id authorization_scope", "") || !sha(m[termPlanDigest]) || !identityString(m["actor_id"]) || !identities(m["authorization_scope"], 1, 64) {
		return invalidDecision()
	}
	ds := array(m["realization_digests"])
	if len(ds) < 1 || len(ds) > 4096 {
		return invalidDecision()
	}
	for _, d := range ds {
		if !sha(d) {
			return invalidDecision()
		}
	}
	return nil
}
func validateObservationDecision(m map[string]any) error {
	if !fields(m, "schema_version execution_attempt_id observation", "snapshot_json observed_at") {
		return invalidDecision()
	}
	if _, ok := m["snapshot_json"]; !ok {
		m["snapshot_json"] = nil
	}
	if m["snapshot_json"] != nil {
		s, ok := m["snapshot_json"].(string)
		if !ok || utf8.RuneCountInString(s) > 16_777_216 {
			return invalidDecision()
		}
	}
	if m["observed_at"] == nil {
		delete(m, "observed_at")
	} else if !timestamp(m["observed_at"]) {
		return invalidDecision()
	}
	return validateObservationMap(object(m["observation"]))
}
func validateObservationMap(m map[string]any) error {
	if err := observationShape(m); err != nil {
		return err
	}
	if err := observationBooleans(m); err != nil {
		return err
	}
	if text(m, "kind") == termExecution && !slices.Contains([]string{termRunning, termSucceeded, termFailed, termCancelled, termTimedOut, termAborted}, text(m, "state")) {
		return invalidDecision()
	}
	if err := observationCollections(m); err != nil {
		return err
	}
	if v, ok := m["verified_compensations"]; ok && !identities(v, 0, 4096) {
		return invalidDecision()
	}
	if v, ok := m["receipt"]; ok {
		return localModel(contractTrialCleanupReceipt, v)
	}
	return observationObligations(m)
}
func observationObligations(m map[string]any) error {
	if v, ok := m["obligation_results"]; ok {
		results, valid := v.(map[string]any)
		if !valid || len(results) > 4096 {
			return invalidDecision()
		}
		owner, err := experimentOwner()
		if err != nil {
			return err
		}
		for key, result := range results {
			admitted, admitErr := admission.AdmitFragment(owner, admission.CleanupObligationResult, result, runtimeIngress())
			if admitErr != nil {
				return invalidDecision()
			}
			results[key] = admitted.Document()
		}
	}
	return nil
}

func observationShape(m map[string]any) error {
	required, optional := "kind evidence", ""
	switch text(m, "kind") {
	case termConfiguration:
		required += " configurations"
	case termExecution:
		required += " state ceased"
		optional = "effects_absent"
		if _, ok := m["effects_absent"]; !ok {
			m["effects_absent"] = false
		}
	case termCapture:
		required += " complete"
	case termCleanup:
		required += " receipt"
		optional = "idempotent_effects verified_compensations"
		if _, ok := m["idempotent_effects"]; !ok {
			m["idempotent_effects"] = false
		}
		if _, ok := m["verified_compensations"]; !ok {
			m["verified_compensations"] = []any{}
		}
	case termRetry:
		required += " ready"
		optional = "obligation_results verified_compensations"
		if _, ok := m["obligation_results"]; !ok {
			m["obligation_results"] = map[string]any{}
		}
		if _, ok := m["verified_compensations"]; !ok {
			m["verified_compensations"] = []any{}
		}
	default:
		return invalidDecision()
	}
	if !fields(m, required, optional) {
		return invalidDecision()
	}
	return nil
}
func observationBooleans(m map[string]any) error {
	for _, key := range []string{"ceased", "effects_absent", "complete", "ready", "idempotent_effects"} {
		if v, ok := m[key]; ok {
			if _, valid := v.(bool); !valid {
				return invalidDecision()
			}
		}
	}
	return nil
}
func observationCollections(m map[string]any) error {
	for key, id := range map[string]string{termEvidence: "experiment-evidence-record-v1", "configurations": "participant-configuration-result-v1"} {
		if v, ok := m[key]; ok {
			items, valid := v.([]any)
			if !valid || len(items) > 4096 {
				return invalidDecision()
			}
			for _, item := range items {
				if err := localModel(id, item); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
func validatePublicationDecision(m map[string]any) error {
	if !fields(m, "schema_version experiment_id validation_status", "state run study failure_codes") {
		return invalidDecision()
	}
	if _, ok := m["state"]; !ok {
		m["state"] = termCandidate
	}
	if _, ok := m["failure_codes"]; !ok {
		m["failure_codes"] = []any{}
	}
	if _, ok := m[termRun]; !ok {
		m[termRun] = nil
	}
	if _, ok := m[termStudy]; !ok {
		m[termStudy] = nil
	}
	if (m[termRun] == nil) == (m[termStudy] == nil) || !slices.Contains([]string{termCandidate, "published"}, text(m, "state")) || !slices.Contains([]string{termPassed, termFailed, termNotPerformed}, text(m, "validation_status")) || !identities(m["failure_codes"], 0, 64) {
		return invalidDecision()
	}
	if m[termRun] != nil {
		return localModel(contractExperimentRun, m[termRun])
	}
	return localModel(contractExperimentStudy, m[termStudy])
}
func validateReplacementDecision(m map[string]any) error {
	if !fields(m, "schema_version experiment_id root_entry_id ordinal plan superseded_run parent_run cleanup_receipts", "") || !identityString(m["root_entry_id"]) || integer(m["ordinal"]) < 1 || integer(m["ordinal"]) > 1000 {
		return invalidDecision()
	}
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	raw, err := json.Marshal(m["plan"])
	if err != nil {
		return invalidDecision()
	}
	if _, err = owner.Validate("admitted-trial-plan-v1", raw, runtimeIngress(), nil); err != nil {
		return err
	}
	for _, key := range []string{"superseded_run", "parent_run"} {
		if err = localModel(contractExperimentRun, m[key]); err != nil {
			return err
		}
	}
	receipts := array(m["cleanup_receipts"])
	if len(receipts) < 1 || len(receipts) > 1000 {
		return invalidDecision()
	}
	for _, receipt := range receipts {
		if err = localModel(contractTrialCleanupReceipt, receipt); err != nil {
			return err
		}
	}
	return nil
}
func decisionMap(d Decision) map[string]any {
	parsed, _ := ingress.Parse(d.JSON(), runtimeIngress(), ingress.Object)
	return object(parsed)
}

//nolint:ireturn // Only the decision owner mints this sealed interface.
func makeDecision(schema string, m map[string]any) (Decision, error) {
	m["schema_version"] = schema
	raw, err := json.Marshal(m)
	if err != nil {
		return nil, invalidDecision()
	}
	return DecodeDecision(raw)
}
