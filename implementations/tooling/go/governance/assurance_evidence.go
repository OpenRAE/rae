package governance

import (
	"slices"
	"strconv"
	"time"
)

func assuranceFulfillmentDelivered(r *repository, id string, value any, kinds []string) ([]string, []Finding) {
	satisfied := []string{}
	findings := []Finding{}
	if value == nil {
		return satisfied, findings
	}
	entries, ok := value.([]any)
	if !ok {
		return satisfied, []Finding{fulfillmentFinding("artifact", id+".delivered_artifacts must be a YAML list")}
	}
	for i, value := range entries {
		prefix := id + ".delivered_artifacts[" + strconv.Itoa(i) + "]"
		item := object(value)
		if item == nil {
			findings = append(findings, fulfillmentFinding("artifact", prefix+" must be a mapping"))
			continue
		}
		kind, textual := item.get("kind").(string)
		validKind := textual && slices.Contains(kinds, kind)
		if !validKind {
			findings = append(findings, fulfillmentFinding("artifact", prefix+".kind must be one of "+pythonRepr(kinds)+"; got "+pythonRepr(item.get("kind"))))
		}
		message := assuranceFulfillmentArtifactPath(r, id, prefix, item.get("path"))
		if message != "" {
			findings = append(findings, fulfillmentFinding("artifact", message))
		} else if validKind {
			satisfied = append(satisfied, kind)
		}
	}
	return satisfied, findings
}
func assuranceFulfillmentArtifactPath(r *repository, id, prefix string, value any) string {
	if !assuranceNonblank(value) {
		return prefix + ".path must be a non-empty repo-relative path"
	}
	selected := pythonStr(value)
	relative, err := r.resolve(selected)
	if err != nil {
		return id + " delivered artifact path escapes the repo root: " + selected
	}
	info, err := r.root.Stat(relative)
	if err != nil || !info.Mode().IsRegular() {
		return id + " delivered artifact path does not exist: " + selected
	}
	if info.Size() == 0 {
		return id + " delivered artifact path is empty: " + selected
	}
	return ""
}

func assuranceFulfillmentWaived(id string, value any, kinds []string) ([]string, []Finding) {
	satisfied := []string{}
	findings := []Finding{}
	if value == nil {
		return satisfied, findings
	}
	entries, ok := value.([]any)
	if !ok {
		return satisfied, []Finding{fulfillmentFinding("waiver", id+".waived_artifacts must be a YAML list when present")}
	}
	for i, value := range entries {
		prefix := id + ".waived_artifacts[" + strconv.Itoa(i) + "]"
		item := object(value)
		if item == nil {
			findings = append(findings, fulfillmentFinding("waiver", prefix+" must be a mapping"))
			continue
		}
		kind, problems := assuranceFulfillmentWaiver(id, prefix, item, kinds)
		findings = append(findings, problems...)
		if kind != nil {
			satisfied = append(satisfied, *kind)
		}
	}
	return satisfied, findings
}
func assuranceFulfillmentWaiver(id, prefix string, item *mapping, kinds []string) (*string, []Finding) {
	findings := []Finding{}
	kind, textual := item.get("kind").(string)
	validKind := textual && slices.Contains(kinds, kind)
	if !validKind {
		findings = append(findings, fulfillmentFinding("waiver", prefix+".kind must be one of "+pythonRepr(kinds)+"; got "+pythonRepr(item.get("kind"))))
	}
	validDate := assuranceWaiverDate(item.get("date"))
	if !validDate {
		findings = append(findings, fulfillmentFinding("waiver", id+" waiver for "+pythonRepr(item.get("kind"))+" must carry an ISO date (YYYY-MM-DD); got "+pythonRepr(item.get("date"))))
	}
	tracking, _ := item.get("tracking").([]any)
	validTracking := slices.ContainsFunc(tracking, assuranceNonblank)
	if !validTracking {
		findings = append(findings, fulfillmentFinding("waiver", id+" waiver for "+pythonRepr(item.get("kind"))+" must name at least one tracking reference"))
	}
	validRationale := assuranceNonblank(item.get("rationale"))
	if !validRationale {
		findings = append(findings, fulfillmentFinding("waiver", id+" waiver for "+pythonRepr(item.get("kind"))+" must carry a non-empty rationale"))
	}
	if validKind && validDate && validTracking && validRationale {
		return &kind, findings
	}
	return nil, findings
}

func assuranceWaiverDate(value any) bool {
	if _, ok := value.(yamlDate); ok {
		return true
	}
	text, ok := value.(string)
	if !ok || len(text) != 10 {
		return false
	}
	date, err := time.Parse("2006-01-02", text)
	return err == nil && date.Year() > 0 && date.Format("2006-01-02") == text
}
