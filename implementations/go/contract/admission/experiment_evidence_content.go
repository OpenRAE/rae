package admission

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

type experimentEvidencePayload struct {
	data      []byte
	checksum  string
	documents map[string]any
}

func experimentEvidenceLimits() ingress.Limits {
	return ingress.Limits{MaxBytes: 64 << 20, MaxDepth: 64}
}

func (s *experimentEvidence) validateContent(requirement, record, artifact any) error {
	if err := evidenceContentMetadata(requirement, record, artifact); err != nil {
		return err
	}
	if err := evidenceLocator(stringAt(artifact, "uri")); err != nil {
		return err
	}
	content, err := s.evidencePayload(artifact)
	if err != nil {
		return err
	}
	if !strings.EqualFold(content.checksum, stringAt(artifact, "checksum", termValue)) {
		return invalid()
	}
	for _, integrity := range stringsOf(at(requirement, "integrity_requirements")) {
		if integrity != "checksum" && (integrity != "sha256-digest" || stringAt(artifact, "checksum", "algorithm") != "sha256") {
			return invalid()
		}
	}
	contract := stringAt(requirement, "output_contract")
	document, present := content.documents[contract]
	if !present {
		document, err = s.owner.evidenceOutput(content.data, stringAt(artifact, "media_type"), contract)
		if err != nil {
			return err
		}
		content.documents[contract] = document
	}
	for _, selector := range stringsOf(at(requirement, "field_selectors")) {
		if _, present := pointerAt(document, selector); !present {
			return invalid()
		}
	}
	return nil
}
func (s *experimentEvidence) evidencePayload(artifact any) (*experimentEvidencePayload, error) {
	identity, err := jsonDigest(artifact)
	if err != nil {
		return nil, err
	}
	content := s.content[identity]
	if content == nil {
		reader := s.readers[stringAt(artifact, termArtifactID)]
		if reader == nil {
			return nil, invalid()
		}
		size, ok := number(at(artifact, "size_bytes"))
		if !ok || !size.IsInt() || !size.Num().IsInt64() || size.Sign() < 0 || size.Num().Int64() > 64<<20 {
			return nil, invalid()
		}
		data, checksum, err := readEvidence(reader, int(size.Num().Int64()), stringAt(artifact, "checksum", "algorithm"))
		if err != nil {
			return nil, err
		}
		content = &experimentEvidencePayload{data: data, checksum: checksum, documents: map[string]any{}}
		s.content[identity] = content
	}
	return content, nil
}

func evidenceContentMetadata(requirement, record, artifact any) error {
	roles := set(at(requirement, "required_artifact_roles"))
	if len(roles) > 0 && !roles[stringAt(artifact, "role")] {
		return invalid()
	}
	if !set(at(requirement, "expected_media_types"))[stringAt(artifact, "media_type")] || !matchingFields(artifact, requirement, "sensitivity") || !matchingFields(artifact, record, "sensitivity") {
		return invalid()
	}
	return nil
}
func evidenceLocator(uri string) error {
	for _, character := range uri {
		if character < 32 || character == 127 {
			return invalid()
		}
	}
	scheme, _, found := strings.Cut(uri, ":")
	absolute := found && len(scheme) > 0 && strings.ContainsRune("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", rune(scheme[0])) && strings.Trim(scheme, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+.-") == ""
	if !absolute {
		path, _, _ := strings.Cut(uri, "?")
		path, _, _ = strings.Cut(path, "#")
		if strings.HasPrefix(uri, "/") || strings.Contains(uri, "\\") {
			return invalid()
		}
		for part := range strings.SplitSeq(path, "/") {
			if part == ".." {
				return invalid()
			}
		}
		uri = "urn:raes-artifact:" + uri
	}
	if urisafety.Check(uri, urisafety.Options{ForbiddenSchemes: []string{"file"}, ForbidFragment: true}) != nil {
		return invalid()
	}
	return nil
}
func readEvidence(reader io.Reader, size int, algorithm string) (data []byte, checksum string, err error) {
	hash, ok := digest.NewChecksum(algorithm)
	if !ok {
		return nil, "", invalid()
	}
	var payload bytes.Buffer
	buffer := make([]byte, 64<<10)
	for payload.Len() <= size {
		n, readErr := readEvidenceChunk(reader, buffer[:min(len(buffer), size+1-payload.Len())])
		if n > 0 {
			_, _ = payload.Write(buffer[:n])
			_, _ = hash.Write(buffer[:n])
		}
		if readErr != nil {
			if !errors.Is(readErr, io.EOF) {
				return nil, "", readErr
			}
			break
		}
		if n == 0 {
			return nil, "", evidenceReaderFailure()
		}
	}
	if payload.Len() != size {
		return nil, "", invalid()
	}
	return payload.Bytes(), hex.EncodeToString(hash.Sum(nil)), nil
}

// Only installed reader calls can panic or return untrusted counts/errors.
func readEvidenceChunk(reader io.Reader, buffer []byte) (n int, err error) {
	defer func() {
		if recover() != nil {
			n = 0
			err = evidenceReaderFailure()
		}
	}()
	n, err = reader.Read(buffer)
	if n < 0 || n > len(buffer) {
		return 0, evidenceReaderFailure()
	}
	if err != nil {
		if errors.Is(err, io.EOF) {
			return n, io.EOF
		}
		return 0, evidenceReaderFailure()
	}
	return n, nil
}
func evidenceReaderFailure() error {
	slog.Error("experiment evidence reader failed", slog.String("failure_class", "foreign"))
	return fault.New(fault.Operational, "experiment-evidence-read-failed", nil)
}
func (e *Validator) evidenceOutput(data []byte, media, contract string) (any, error) {
	root := ingress.Object
	switch contract {
	case termExperimentEvidenceRecordV1:
		if media != mediaApplicationJSON {
			return nil, invalid()
		}
	case termParticipantBehaviorHistoryEventStreamV1:
		root = ingress.Array
	default:
		return nil, invalid()
	}
	var document any
	var err error
	switch {
	case media == mediaApplicationJSON:
		document, err = ingress.Parse(data, experimentEvidenceLimits(), root)
	case media == "application/jsonl" && root == ingress.Array:
		document, err = evidenceJSONLines(data)
	default:
		return nil, invalid()
	}
	if err != nil {
		return nil, invalid()
	}
	raw, err := json.Marshal(document)
	if err != nil || len(raw) > 64<<20 {
		return nil, invalid()
	}
	if err = e.low.CheckLocal(contract, raw, experimentEvidenceLimits()); err != nil {
		return nil, err
	}
	if err = e.checkModels(contract, raw, experimentEvidenceLimits()); err != nil {
		return nil, err
	}
	return document, nil
}
func evidenceJSONLines(data []byte) ([]any, error) {
	// splitlines drops one final line terminator; interior empty lines are refused.
	lines := evidenceSplitLines(data)

	if len(lines) == 0 {
		return nil, invalid()
	}
	result := make([]any, 0, len(lines))
	for _, line := range lines {
		line = bytes.TrimSuffix(line, []byte{'\r'})
		if len(bytes.TrimSpace(line)) == 0 {
			return nil, invalid()
		}
		value, err := ingress.Parse(line, experimentEvidenceLimits(), ingress.Object)
		if err != nil {
			return nil, err
		}
		result = append(result, value)
	}
	return result, nil
}

func evidenceSplitLines(data []byte) [][]byte {
	lines := [][]byte{}
	for len(data) > 0 {
		index := bytes.IndexAny(data, "\r\n")
		if index < 0 {
			return append(lines, data)
		}
		lines = append(lines, data[:index])
		width := 1
		if data[index] == '\r' && index+1 < len(data) && data[index+1] == '\n' {
			width = 2
		}
		data = data[index+width:]
	}
	return lines
}
