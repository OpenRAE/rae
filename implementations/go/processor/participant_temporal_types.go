package processor

import "encoding/json"

type participantCoordinate struct {
	Segment   json.Number `json:"segment"`
	Tick      json.Number `json:"tick"`
	Microstep json.Number `json:"microstep"`
}
type participantTemporalBinding struct {
	Profile                    string                 `json:"profile"`
	ActionContractAddress      string                 `json:"action_contract_address"`
	TemporalID                 string                 `json:"temporal_id"`
	TemporalKind               string                 `json:"temporal_kind"`
	ClockAddress               string                 `json:"clock_address"`
	ConstraintAddress          string                 `json:"constraint_address"`
	EventPoint                 string                 `json:"event_point"`
	EvidenceMode               string                 `json:"evidence_mode"`
	Start                      *participantCoordinate `json:"start,omitempty"`
	End                        participantCoordinate  `json:"end"`
	ConditionPreconditionID    *string                `json:"condition_precondition_id,omitempty"`
	ObservationBoundaryAddress *string                `json:"observation_boundary_address,omitempty"`
	ContractDigest             string                 `json:"contract_digest"`
	TimeDomain                 string                 `json:"time_domain"`
	ClockAuthority             string                 `json:"clock_authority"`
	EventPoints                []string               `json:"event_points"`
	BackendDisclosureRefs      []string               `json:"backend_disclosure_refs"`
	ResetBoundary              string                 `json:"reset_boundary"`
	ReplayBoundary             string                 `json:"replay_boundary"`
}
