package governance

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"net/url"
	"slices"
	"strings"
)

type vocabularyInput struct {
	profile   vocabularyProfile
	source    *mapping
	selection sourceSelection
}

func (c *checker) remoteVocabularies(ctx context.Context, r *repository, inputs []vocabularyInput) ([]string, error) {
	// Autonomous verification binds both reviewed selections before either transfer.
	for i := range inputs {
		id := vocabularyArtifactID(inputs[i].profile)
		selection, err := selectSourceSnapshot(r, id, inputs[i].profile.value(sourceVersionField))
		if err != nil {
			return nil, err
		}
		inputs[i].selection = selection
	}
	messages := []string{}
	for _, input := range inputs {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		local := c.request.LocalInput
		switch input.profile.label {
		case activityVocabulary:
			local = c.request.ActivityStreamsLocalInput
		case fipaVocabulary:
			local = c.request.FIPALocalInput
		}
		findings, err := verifyVocabularyInput(ctx, input, local)
		if err != nil {
			return nil, err
		}
		messages = append(messages, findings...)
		if c.request.Tool == autonomousVocabularyCheck && len(findings) > 0 {
			break
		}
	}
	return messages, nil
}

func vocabularyArtifactID(profile vocabularyProfile) string {
	switch profile.label {
	case attackVocabulary:
		return "attack-enterprise-tactics-snapshot"
	case atlasVocabulary:
		return "atlas-tactics-snapshot"
	case nistVocabulary:
		return "nist-csf-defensive-categories-snapshot"
	case activityVocabulary:
		return "w3c-activitystreams-activity-types-snapshot"
	case fipaVocabulary:
		return "fipa-communicative-acts-snapshot"
	default:
		return ""
	}
}

func verifyVocabularyInput(ctx context.Context, input vocabularyInput, local string) ([]string, error) {
	if message := vocabularyRemoteURL(input); message != "" {
		return []string{message}, nil
	}
	data, err := acquireLockedBytes(ctx, vocabularyArtifactID(input.profile), input.selection.url, input.selection.raw, local)
	if err != nil {
		if acquisition, expected := errors.AsType[artifactAcquisitionError](err); expected {
			return []string{input.profile.path + ": " + acquisition.Error()}, nil
		}
		return nil, err
	}
	return compareVocabularyBytes(input.profile, input.source, data)
}

func vocabularyRemoteURL(input vocabularyInput) string {
	profile, source, selected := input.profile, input.source, input.selection.url
	field, description := sourceURLField, "source URL"
	if profile.label == fipaVocabulary {
		field, description = "source_artifact_url", "source artifact URL"
	}
	if source.get(field) != selected {
		return profile.path + ": " + description + " differs from the reviewed lock selection"
	}
	parsed, err := url.Parse(selected)
	valid := err == nil && parsed.Scheme == "https"
	message := ""
	switch profile.label {
	case attackVocabulary:
		valid = valid && parsed.Host == "raw.githubusercontent.com"
		message = "remote verification URL must stay pinned to raw.githubusercontent.com HTTPS"
	case atlasVocabulary:
		valid = valid && parsed.Host == "github.com" && parsed.EscapedPath() == "/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml"
		message = "remote verification URL must stay pinned to the v2026.06 GitHub release asset"
	case nistVocabulary:
		valid = valid && parsed.Host == "csrc.nist.gov"
		message = "remote verification URL must stay on csrc.nist.gov HTTPS"
	case activityVocabulary:
		valid = valid && strings.EqualFold(parsed.Hostname(), "www.w3.org")
		message = "remote verification URL must stay on the allowlisted official HTTPS host"
	case fipaVocabulary:
		valid = valid && strings.EqualFold(parsed.Hostname(), "www.fipa.org")
		message = "remote verification URL must stay on the allowlisted official HTTPS host"
	}
	if !valid {
		return profile.path + ": " + message
	}
	return ""
}

func compareVocabularyBytes(profile vocabularyProfile, source *mapping, data []byte) ([]string, error) {
	messages := []string{}
	if profile.label == nistVocabulary {
		return compareNISTBytes(profile, source, data)
	}
	messages = append(messages, vocabularyRawDigestFindings(profile, source, data)...)

	switch profile.label {
	case attackVocabulary, atlasVocabulary:
		rows, err := extractTacticSnapshot(profile.label, data)
		if err != nil {
			return nil, err
		}
		if !publicationEqual(rows, sourceTacticRows(profile.label, source)) {
			description := "pinned upstream STIX bundle"
			if profile.label == atlasVocabulary {
				description = "pinned upstream ATLAS YAML"
			}
			messages = append(messages, profile.path+": tactic snapshot differs from "+description)
		}
	case activityVocabulary:
		names, err := extractActivityNames(data)
		if err != nil {
			return nil, err
		}
		if !slices.Equal(names, activityTypeNames()) {
			messages = append(messages, profile.path+": retrieved Activity type order/content differs from snapshot")
		}
	}
	return messages, nil
}

func vocabularyRawDigestFindings(profile vocabularyProfile, source *mapping, data []byte) []string {
	messages := []string{}
	digest := "sha256:" + fmt.Sprintf("%x", sha256.Sum256(data))
	if digest != source.get(sourceDigestField) {
		message := "source_digest differs from the reviewed lock manifest"
		switch profile.label {
		case activityVocabulary:
			message = "retrieved Recommendation bytes differ from source_digest"
		case fipaVocabulary:
			message = "retrieved specification artifact bytes differ from source_digest"
		}
		messages = append(messages, profile.path+": "+message)
	}
	return messages
}

func sourceTacticRows(label string, source *mapping) []any {
	fields := []string{tacticIDField, shortnameField, nameField, descriptionField, urlField, "stix_id"}
	if label == atlasVocabulary {
		fields = []string{tacticIDField, shortnameField, nameField, descriptionField, urlField, "position", uuidField, "created_date", "modified_date", "attack_reference_id", "attack_reference_url"}
	}
	rows := []any{}
	for _, item := range mappingItems(source.get("tactics")) {
		row := newMapping()
		for _, field := range fields {
			row.set(field, item.get(field))
		}
		rows = append(rows, row)
	}
	return rows
}
