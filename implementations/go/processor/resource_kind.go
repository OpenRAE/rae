package processor

import (
	"encoding/json"
	"fmt"

	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

// participantResourceKind is a comparable private wire union. Its object
// member is a pinned coordinate admitted by the SDL or manifest owner.
type participantResourceKind string

type resourceCoordinate struct {
	Namespace        string `json:"namespace"`
	ProfileID        string `json:"profile_id"`
	Revision         string `json:"revision"`
	Authority        string `json:"authority"`
	DefinitionDigest string `json:"definition_digest"`
}

func (kind *participantResourceKind) UnmarshalJSON(raw []byte) error {
	var literal string
	if json.Unmarshal(raw, &literal) == nil {
		*kind = participantResourceKind(literal)
		return nil
	}
	var coordinate resourceCoordinate
	if json.Unmarshal(raw, &coordinate) != nil || coordinate.Namespace == "" || coordinate.ProfileID == "" || coordinate.Revision == "" || coordinate.Authority == "" || coordinate.DefinitionDigest == "" {
		return invalidCompiled()
	}
	canonical, err := json.Marshal(coordinate)
	if err != nil {
		return err
	}
	*kind = participantResourceKind(canonical)
	return nil
}

func (kind participantResourceKind) MarshalJSON() ([]byte, error) {
	if len(kind) > 0 && kind[0] == '{' {
		return []byte(kind), nil
	}
	return json.Marshal(string(kind))
}

func (kind participantResourceKind) label() string {
	if len(kind) == 0 || kind[0] != '{' {
		return string(kind)
	}
	var coordinate resourceCoordinate
	if json.Unmarshal([]byte(kind), &coordinate) != nil {
		panic("processor: invalid owned resource coordinate")
	}
	return fmt.Sprintf("namespace=%s authority=%s profile_id=%s revision=%s definition_digest=%s", pyrepr.Quote(coordinate.Namespace), pyrepr.Quote(coordinate.Authority), pyrepr.Quote(coordinate.ProfileID), pyrepr.Quote(coordinate.Revision), pyrepr.Quote(coordinate.DefinitionDigest))
}
