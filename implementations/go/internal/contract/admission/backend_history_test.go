package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestBackendHistoryPreservesAcknowledgementAndTerminalEvidence(t *testing.T) {
	e := boundTestOwner(t)
	c := mixedStageFixtureContext(t, e, "mixed-edge")
	request, err := e.backendDocument("backend-operation-request-v1", c.request)
	if err != nil {
		t.Fatal(err)
	}
	responses, err := e.backendDocuments("backend-operation-response-v1", c.responses, 1024)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = backendTranscript(request, responses, nil); err != nil {
		t.Fatal(err)
	}
	duplicate := append(append([]any{}, responses...), responses[1])
	if _, err = backendTranscript(request, duplicate, nil); err != nil {
		t.Fatal("retransmission changed terminal state", err)
	}
	for _, name := range []string{"stale", "changed-sequence", "no-acknowledgement", "after-terminal"} {
		t.Run(name, func(t *testing.T) {
			changed := append([]any{}, responses...)
			switch name {
			case "stale":
				changed[0], changed[1] = changed[1], changed[0]
			case "changed-sequence":
				copyValue := decodeRuleObject(t, string(controlJSON(t, changed[len(changed)-1])))
				object(copyValue)["sequence"] = at(changed[1], "sequence")
				changed = append(changed, copyValue)
			case "no-acknowledgement":
				changed = append(changed[:1], changed[2:]...)
			case "after-terminal":
				copyValue := decodeRuleObject(t, string(controlJSON(t, changed[1])))
				object(copyValue)["sequence"] = json.Number("99")
				changed = append(changed, copyValue)
			}
			if _, err := backendTranscript(request, changed, nil); err == nil {
				t.Fatal("accepted invalid history")
			}
		})
	}
}

func TestMixedStagesRefuseSubstitutedProducersAndFalseSuccess(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	c := mixedStageFixtureContext(t, e, "mixed-edge")
	v, err := ingress.Parse(c.reports[0], limits, ingress.Object)
	if err != nil {
		t.Fatal(err)
	}
	object(at(v, "stage", "producer"))["service_ref"] = "uninstalled-service"
	c.reports[0] = controlJSON(t, v)
	if _, err = e.Validate("mixed-backend-stage-report-v1", c.reports[0], limits, c); err == nil {
		t.Fatal("accepted uninstalled stage producer")
	}
	c = mixedStageFixtureContext(t, e, "mixed-edge")
	c.snapshot.PostTimeState = validation.Value{}
	if _, err = e.Validate("mixed-backend-stage-report-v1", c.reports[0], limits, c); err == nil {
		t.Fatal("accepted success without post-invocation time")
	}
}
