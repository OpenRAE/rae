package admission

import (
	"encoding/json"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) experimentLocalRules() map[string]definition {
	return map[string]definition{
		"capture-window-interval-valid":                  {check: captureInterval},
		"capture-requirement-key-matches-requirement-id": {check: captureKeys},
		"capture-media-type-provable":                    {check: captureMedia},
		"derived-measure-generated-at-valid":             {check: func(i validation.Invocation) error { return timestamps(i.Instance, "generated_at") }},
		"derived-measure-reported-value-present": {check: func(i validation.Invocation) error {
			return require((stringAt(i.Instance, "value_status") == termReported) == (at(i.Instance, "value") != nil))
		}},
		"evidence-record-captured-at-valid":   {check: func(i validation.Invocation) error { return timestamps(i.Instance, "captured_at") }},
		"evidence-record-raw-content-present": {check: evidenceContent},
		"metric-definition-key-matches-metric-id": {check: func(i validation.Invocation) error {
			return require(keyed(at(i.Instance, "metric_definitions"), "metric_id"))
		}},
		"participant-configuration-digest-valid":        {check: configurationDigest},
		"ended-at-not-before-started-at":                {check: runInterval},
		"task-archival-times-rfc3339-valid":             {check: func(i validation.Invocation) error { return artifactTimes(at(i.Instance, "artifact_refs")) }},
		"apparatus-archival-times-rfc3339-valid":        {check: apparatusTimes},
		"run-archival-times-rfc3339-valid":              {check: runTimes},
		"study-archival-times-rfc3339-valid":            {check: studyTimes},
		"trial-replacement-policy-explicit-and-bounded": {check: replacementPolicy},
		"analysis-plan-substantive-methods-required": {check: func(i validation.Invocation) error {
			return require(set(at(i.Instance, "metrics"))[stringAt(i.Instance, "primary_metric")])
		}},
		"realized-form-disclosure-substantive": {check: realizedDisclosure},
		"run-traceability-refs-unique":         {check: traceabilityRefs},
	}
}

func timestamps(v any, fields ...string) error {
	for _, field := range fields {
		if value := at(v, field); value != nil {
			if _, err := timestamp.ParseRFC3339(codeContractTime, text(value)); err != nil {
				return invalid()
			}
		}
	}
	return nil
}
func artifactTimes(v any) error {
	for _, artifact := range array(v) {
		if err := timestamps(artifact, "created_at"); err != nil {
			return err
		}
	}
	return nil
}
func interval(v any, start, end string) error {
	left, right := at(v, start), at(v, end)
	if left == nil || right == nil {
		return nil
	}
	a, err := timestamp.ParseRFC3339(codeContractTime, text(left))
	if err != nil {
		return invalid()
	}
	b, err := timestamp.ParseRFC3339(codeContractTime, text(right))
	if err != nil {
		return invalid()
	}
	return require(!b.Instant().Before(a.Instant()))
}
func captureInterval(i validation.Invocation) error {
	return interval(i.Instance, "starts_at", "ends_at")
}
func runInterval(i validation.Invocation) error {
	if err := timestamps(i.Instance, "started_at", "ended_at"); err != nil {
		return err
	}
	return interval(i.Instance, "started_at", "ended_at")
}
func apparatusTimes(i validation.Invocation) error {
	if err := timestamps(i.Instance, "declared_at"); err != nil {
		return err
	}
	return artifactTimes(at(i.Instance, "observed_setup_evidence"))
}
func runTimes(i validation.Invocation) error {
	if err := timestamps(i.Instance, "started_at", "ended_at"); err != nil {
		return err
	}
	if err := timestamps(at(i.Instance, "invalidation"), "invalidated_at"); err != nil {
		return err
	}
	return artifactTimes(at(i.Instance, "evidence_artifacts"))
}
func studyTimes(i validation.Invocation) error {
	if err := artifactTimes(at(i.Instance, "report_artifacts")); err != nil {
		return err
	}
	return artifactTimes(at(i.Instance, "export_artifacts"))
}
func captureKeys(i validation.Invocation) error {
	var ids []string
	for _, window := range array(at(i.Instance, "capture_windows")) {
		ids = append(ids, stringAt(window, "window_id"))
	}
	if !unique(ids) || !keyed(at(i.Instance, "capture_requirements"), "requirement_id") {
		return invalid()
	}
	windows := map[string]bool{}
	for _, id := range ids {
		windows[id] = true
	}
	for _, requirement := range object(at(i.Instance, "capture_requirements")) {
		if !subset(stringsOf(at(requirement, "window_refs")), windows) {
			return invalid()
		}
	}
	return nil
}
func captureMedia(i validation.Invocation) error {
	if requirements := object(at(i.Instance, "capture_requirements")); requirements != nil {
		for _, requirement := range requirements {
			if err := mediaDeclaration(stringAt(requirement, "output_contract"), stringsOf(at(requirement, "expected_media_types"))); err != nil {
				return err
			}
		}
		return nil
	}
	return mediaDeclaration(stringAt(i.Instance, "output_contract"), stringsOf(at(i.Instance, "expected_media_types")))
}
func mediaDeclaration(id string, media []string) error {
	if id == "" && len(media) == 0 {
		return nil
	}
	allowed := map[string]bool{"application/json": true}
	switch id {
	case "":
		allowed["application/jsonl"] = true
	case termExperimentEvidenceRecordV1:
	case termParticipantBehaviorHistoryEventStreamV1:
		allowed["application/jsonl"] = true
	default:
		return invalid()
	}
	return require(subset(media, allowed))
}
func evidenceContent(i validation.Invocation) error {
	raw := at(i.Instance, "raw_content")
	if at(raw, "artifact_ref") == nil && at(raw, "content_uri") == nil && at(raw, "payload_summary") == nil {
		return invalid()
	}
	if at(raw, "content_uri") != nil && at(raw, "content_checksum") == nil {
		return invalid()
	}
	redacted := stringAt(i.Instance, "redaction_state") != postureNone
	if redacted && at(raw, "loss_disclosure") == nil {
		return invalid()
	}
	return require(redacted == (at(i.Instance, "redaction_policy") != nil))
}
func replacementPolicy(i validation.Invocation) error {
	limit, ok := number(at(i.Instance, "max_replacements"))
	if !ok {
		return invalid()
	}
	triggers := stringsOf(at(i.Instance, "replace_on"))
	return require(unique(triggers) && (limit.Sign() > 0) == (len(triggers) > 0))
}
func realizedDisclosure(i validation.Invocation) error {
	if at(i.Instance, "realized_ref") == nil && at(i.Instance, "realized_value_summary") == nil {
		return invalid()
	}
	kind := stringAt(i.Instance, "realized_by_ref", fieldRefKind)
	switch stringAt(i.Instance, "basis") {
	case "processor-realized":
		if kind != kindProcessor {
			return invalid()
		}
	case termBackendRealized:
		if kind != kindBackend {
			return invalid()
		}
	}
	return require(uniqueReferences(at(i.Instance, fieldEvidenceRefs)))
}
func referenceKey(v any) string {
	return join(stringAt(v, fieldRefKind), stringAt(v, fieldRefID), stringAt(v, fieldRefVersion), strings.ToLower(stringAt(v, "ref_digest")), stringAt(v, "ref_path"), referenceSubject(v))
}
func referenceSubject(v any) string {
	if subject := at(v, "subject_ref"); subject != nil {
		return referenceKey(subject)
	}
	return ""
}
func uniqueReferences(v any) bool {
	keys := make([]string, 0, len(array(v)))
	for _, ref := range array(v) {
		keys = append(keys, referenceKey(ref))
	}
	return unique(keys)
}
func traceabilityRefs(i validation.Invocation) error {
	for _, field := range []string{"capture_spec_refs", "evidence_record_refs", "derived_measure_refs", "claim_refs"} {
		if !uniqueReferences(at(i.Instance, field)) {
			return invalid()
		}
	}
	return require(len(array(at(i.Instance, "claim_refs"))) == 0 || len(array(at(i.Instance, "derived_measure_refs"))) > 0)
}
func configurationDigest(i validation.Invocation) error {
	configuration := maps.Clone(object(at(i.Instance, termConfiguration)))
	values := make([]any, 0, len(array(configuration["values"])))
	for _, raw := range array(configuration["values"]) {
		value := maps.Clone(object(raw))
		if value["control_context_selection"] == nil {
			delete(value, "control_context_selection")
		}
		values = append(values, value)
	}
	configuration["values"] = values
	data, err := json.Marshal(configuration)
	if err != nil {
		return invalid()
	}
	canonical, err := canonjson.JCS(data)
	if err != nil {
		return invalid()
	}
	return require(stringAt(i.Instance, "configuration_digest") == digest.SHA256(canonical))
}
