package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// FlowSink fixes the complete destination and audience of a trusted sink.
type FlowSink struct {
	Kind        string `json:"Kind"`
	Reference   string `json:"Reference"`
	Destination string `json:"Destination"`
	Audience    string `json:"Audience"`
}

// FlowReleaseAuthority identifies the full independently authorized release scope.
type FlowReleaseAuthority struct {
	Kind        string `json:"Kind"`
	Authority   string `json:"Authority"`
	Revision    string `json:"Revision"`
	Sink        string `json:"Sink"`
	Destination string `json:"Destination"`
	Audience    string `json:"Audience"`
}

// FlowOwnerReleaseAuthority binds one owner obligation to one complete release.
type FlowOwnerReleaseAuthority struct {
	ReleaseDigest string `json:"ReleaseDigest"`
	Owner         string `json:"Owner"`
	Obligation    string `json:"Obligation"`
}

// FlowOwnerSink supplies resolved principals and the sink's integrity posture.
type FlowOwnerSink struct {
	Readers                   []string `json:"Readers"`
	AcceptsUntrustedIntegrity bool     `json:"AcceptsUntrustedIntegrity"`
}

// FlowActionResolution supplies the exact action admission disposition.
type FlowActionResolution struct {
	Reference             string   `json:"Reference"`
	ParticipantAddress    string   `json:"ParticipantAddress"`
	EpisodeID             string   `json:"EpisodeID"`
	ActionContractAddress string   `json:"ActionContractAddress"`
	ActionInstanceID      string   `json:"ActionInstanceID"`
	Sink                  FlowSink `json:"Sink"`
	Disposition           string   `json:"Disposition"`
}

// FlowCapabilityResolution supplies the exact capability disposition.
type FlowCapabilityResolution struct {
	Reference          string   `json:"Reference"`
	ParticipantAddress string   `json:"ParticipantAddress"`
	EpisodeID          string   `json:"EpisodeID"`
	Disposition        string   `json:"Disposition"`
	Sink               FlowSink `json:"Sink"`
}

// FlowHistoryResolution supplies the exact history-head freshness disposition.
type FlowHistoryResolution struct {
	ParticipantAddress string   `json:"ParticipantAddress"`
	EpisodeID          string   `json:"EpisodeID"`
	Disposition        string   `json:"Disposition"`
	Sink               FlowSink `json:"Sink"`
	Heads              []string `json:"Heads"`
}

// FlowActionSelection retains the complete normalized action meaning. Argument
// names use a map because their portable representation is canonical name order.
type FlowActionSelection struct {
	ActionContractAddress       string                     `json:"ActionContractAddress"`
	ArgumentShapeRef            string                     `json:"ArgumentShapeRef"`
	ProposalRef                 string                     `json:"ProposalRef"`
	Arguments                   map[string]json.RawMessage `json:"Arguments"`
	DefaultedArgumentNames      []string                   `json:"DefaultedArgumentNames"`
	OmittedArgumentNames        []string                   `json:"OmittedArgumentNames"`
	NormalizationDisclosureRefs []string                   `json:"NormalizationDisclosureRefs"`
	OmissionDisclosureRefs      []string                   `json:"OmissionDisclosureRefs"`
	DefaultDisclosureRefs       []string                   `json:"DefaultDisclosureRefs"`
	LossDisclosureRefs          []string                   `json:"LossDisclosureRefs"`
}

// FlowResourceRequirement is the compiled owner's typed measurement requirement.
type FlowResourceRequirement struct {
	BudgetStateRef  string          `json:"BudgetStateRef"`
	Unit            string          `json:"Unit"`
	MeterProfileRef string          `json:"MeterProfileRef"`
	ResourceKind    json.RawMessage `json:"ResourceKind"`
	Reserved        json.Number     `json:"Reserved"`
}

// FlowActionRequest retains all fields required by action admission validation.
// Optional model bytes use published runtime-snapshot or experiment-run fragments.
type FlowActionRequest struct {
	ParticipantAddress              string                    `json:"ParticipantAddress"`
	ActionContractAddress           string                    `json:"ActionContractAddress"`
	ObservationBoundaryAddress      string                    `json:"ObservationBoundaryAddress"`
	ActionInstanceID                string                    `json:"ActionInstanceID"`
	Manifest                        validation.Value          `json:"Manifest"`
	ImplementationSelection         []byte                    `json:"ImplementationSelection"`
	ActionResult                    []byte                    `json:"ActionResult"`
	Selection                       *FlowActionSelection      `json:"Selection"`
	EvidenceRefs                    []string                  `json:"EvidenceRefs"`
	VisibleRefs                     []string                  `json:"VisibleRefs"`
	DisclosedRefs                   []string                  `json:"DisclosedRefs"`
	ObservationBoundaryEvidenceRefs []string                  `json:"ObservationBoundaryEvidenceRefs"`
	TemporalContexts                [][]byte                  `json:"TemporalContexts"`
	TemporalEvidence                [][]byte                  `json:"TemporalEvidence"`
	StateTransitionKind             string                    `json:"StateTransitionKind"`
	PostStateDigest                 string                    `json:"PostStateDigest"`
	RequiresTerminalOutcome         bool                      `json:"RequiresTerminalOutcome"`
	TargetAddresses                 []string                  `json:"TargetAddresses"`
	ExecutionScopeRef               string                    `json:"ExecutionScopeRef"`
	ExecutionGeneration             *json.Number              `json:"ExecutionGeneration"`
	ResourceRequirements            []FlowResourceRequirement `json:"ResourceRequirements"`
}

// FlowControlSnapshot contains independent incumbent and owner resolutions.
// Action-selection keys are action contract and proposal references.
type FlowControlSnapshot struct {
	Profile                 []byte                              `json:"Profile"`
	SourceLabels            map[string][]byte                   `json:"SourceLabels"`
	PolicyCuts              map[string][]byte                   `json:"PolicyCuts"`
	ReleaseAuthorities      []FlowReleaseAuthority              `json:"ReleaseAuthorities"`
	KnownSinks              []FlowSink                          `json:"KnownSinks"`
	RuntimeFactPlanes       map[string]validation.Value         `json:"RuntimeFactPlanes"`
	ActionSelections        map[[2]string]FlowActionSelection   `json:"ActionSelections"`
	ActionAdmissions        map[string]FlowActionRequest        `json:"ActionAdmissions"`
	ActionResolutions       map[string]FlowActionResolution     `json:"ActionResolutions"`
	CapabilityResolutions   map[string]FlowCapabilityResolution `json:"CapabilityResolutions"`
	HistoryResolutions      []FlowHistoryResolution             `json:"HistoryResolutions"`
	OwnerReleaseAuthorities []FlowOwnerReleaseAuthority         `json:"OwnerReleaseAuthorities"`
	OwnerSinks              map[FlowSink]FlowOwnerSink          `json:"OwnerSinks"`
}

// FlowControlContext supplies exact trusted state. Admission does not resolve
// references, load code or execute a release operation through this interface.
type FlowControlContext interface {
	CrossingContext
	ControlOccurrenceContext
	FlowControlSnapshot() FlowControlSnapshot
}

type flowControl struct {
	owner                                        *Validator
	context                                      FlowControlContext
	snapshot                                     FlowControlSnapshot
	profile                                      any
	labels, cuts, planes, selections, admissions map[string]any
	crossings                                    *crossingIndex
	controls                                     map[string]any
}
