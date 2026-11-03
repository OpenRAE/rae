package admission

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) materializationArchiveRules() map[string]definition {
	return map[string]definition{"materialization-archive-byte-and-lineage-binding": {check: e.materializationArchive, contextual: true, requiresContext: true}}
}

func (e *Validator) materializationArchive(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(MaterializationArchiveContext)
	if !ok {
		return contextRequired()
	}
	source := context.ArchivedMaterializationSDL()
	compiled, err := e.materializationCompile(context, MaterializationCompileRequest{ContractID: termMaterializedScenarioV1, Source: source})
	if err != nil {
		return err
	}
	v, err := e.defaulted("materialization-archive-record-v1", i.Instance)
	if err != nil {
		return err
	}
	if err = archiveRecordLocal(v); err != nil {
		return err
	}
	provenance := at(compiled.full, "materialization_provenance")
	identity, err := jsonDigest(map[string]any{"profile": "raes-sdl-materialized/v1", "scenario": compiled.document})
	if err != nil {
		return err
	}
	if !matchingFields(v, provenance, "inventory", "run_id", "operation_id") || !equal(at(v, "reference", "ref_id"), at(provenance, "attestation_id")) || stringAt(v, "reference", "ref_digest") != identity {
		return invalid()
	}
	path := "runs/" + stringAt(provenance, "run_id") + "/attestations/" + stringAt(provenance, "attestation_id") + ".sdl"
	if stringAt(v, "reference", "ref_path") != path || stringAt(v, "artifact", "checksum", "value") != strings.TrimPrefix(digest.SHA256(source), "sha256:") || !numericEqual(at(v, "artifact", "size_bytes"), json.Number(strconv.Itoa(len(source)))) || !equal(at(v, "artifact", "source"), at(provenance, "producer", termName)) {
		return invalid()
	}
	created, err := materializationISO(stringAt(provenance, "recorded_at"))
	if err != nil {
		return err
	}
	return require(stringAt(v, "artifact", "created_at") == created)
}

func materializationISO(value string) (string, error) {
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return "", invalid()
	}
	result := parsed.Format("2006-01-02T15:04:05")
	if microseconds := parsed.Nanosecond() / 1000; microseconds != 0 {
		result += fmt.Sprintf(".%06d", microseconds)
	}
	return result + parsed.Format("-07:00"), nil
}
