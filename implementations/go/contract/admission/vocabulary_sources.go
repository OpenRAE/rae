package admission

import (
	"encoding/json"
	"strconv"
)

func vocabularySource(id string, v any) (bool, error) {
	switch id {
	case "attack-enterprise-tactics-source-v1":
		return true, sourceUnique(array(at(v, "tactics")), "tactic_id", "shortname")
	case "atlas-tactics-source-v1":
		rows := array(at(v, "tactics"))
		if err := sourceUnique(rows, "tactic_id", "shortname"); err != nil {
			return true, err
		}
		return true, sourcePositions(rows, false)
	case "nist-csf-defensive-categories-source-v1":
		return true, sourceUnique(array(at(v, "categories")), "category_id", "term_id")
	case "w3c-activitystreams-activity-types-source-v1":
		return true, activitySource(v)
	case "fipa-communicative-acts-source-v1":
		rows := array(at(v, "communicative_acts"))
		if err := sourceUnique(rows, "concept_id"); err != nil {
			return true, err
		}
		return true, sourcePositions(rows, true)
	default:
		return false, nil
	}
}
func sourceUnique(rows []any, fields ...string) error {
	for _, field := range fields {
		if len(rowSet(rows, field)) != len(rows) {
			return invalid()
		}
	}
	return nil
}
func sourcePositions(rows []any, contiguous bool) error {
	var previous any
	for index, row := range rows {
		position := at(row, "position")
		if contiguous {
			if !numericEqual(position, json.Number(strconv.Itoa(index+1))) {
				return invalid()
			}
		} else if index > 0 && !numericGreater(position, previous) {
			return invalid()
		}
		previous = position
	}
	return nil
}
func activitySource(v any) error {
	rows := array(at(v, "activity_types"))
	if err := sourceUnique(rows, "type_name", "concept_id"); err != nil {
		return err
	}
	if err := sourcePositions(rows, true); err != nil {
		return err
	}
	for _, row := range rows {
		if stringAt(row, "concept_id") != "https://www.w3.org/ns/activitystreams#"+stringAt(row, "type_name") {
			return invalid()
		}
	}
	return nil
}
