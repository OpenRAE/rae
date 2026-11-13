// Package comparison implements pure governed artifact comparison and bounded impact analysis.
package comparison

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// Artifact is an immutable artifact admitted by its exact native owner.
type Artifact interface{ artifact() }

// Options supplies the complete declared scopes and digest-only context evidence.
type Options struct {
	BeforeScope, AfterScope []Artifact
	TransformationReport    validation.Value
	EvidenceDigests         []string
}

type artifact struct {
	kind, name, version, schema, digest string
	projections                         map[string]ownerProjection
}

func (*artifact) artifact() {}

type ownerProjection struct {
	identity     string
	subjects     []subject
	dependencies []dependency
}
type subject struct {
	identity, representation, structural, semantic, structuralProfile, semanticProfile string
}
type dependency struct{ dependent, target, rule, provenance string }

type representationData struct {
	Profile    string `json:"profile"`
	MediaType  string `json:"media_type"`
	ByteDigest string `json:"byte_digest"`
}
type coordinate struct {
	Kind              string              `json:"artifact_kind"`
	Phase             string              `json:"lifecycle_phase"`
	Identity          string              `json:"canonical_identity"`
	Canonicalization  string              `json:"canonicalization_profile"`
	Digest            string              `json:"canonical_digest"`
	Exact             *representationData `json:"exact_representation"`
	SourceProfile     string              `json:"source_profile,omitempty"`
	ProvenanceProfile string              `json:"provenance_profile,omitempty"`
	Schema            string              `json:"schema_version,omitempty"`
	ScenarioID        string              `json:"scenario_id,omitempty"`
	ScenarioVersion   string              `json:"scenario_version,omitempty"`
	ModuleID          string              `json:"module_id,omitempty"`
	ModuleVersion     string              `json:"module_version,omitempty"`
	TaskID            string              `json:"task_id,omitempty"`
	TaskVersion       string              `json:"task_version,omitempty"`
	RunID             string              `json:"run_id,omitempty"`
	RunVersion        string              `json:"run_version,omitempty"`
	CaptureID         string              `json:"capture_spec_id,omitempty"`
	SpecVersion       string              `json:"spec_version,omitempty"`
	StudyID           string              `json:"study_id,omitempty"`
	StudyVersion      string              `json:"study_version,omitempty"`
	BindingID         string              `json:"binding_set_id,omitempty"`
	BindingVersion    string              `json:"binding_set_version,omitempty"`
}
type scope struct {
	ID     string       `json:"scope_id"`
	Policy string       `json:"closure_policy"`
	Status string       `json:"closure_status"`
	Roots  []string     `json:"traversal_roots"`
	Before []coordinate `json:"before_artifacts"`
	After  []coordinate `json:"after_artifacts"`
	Digest string       `json:"scope_digest"`
}
type limits struct {
	Subjects    int `json:"max_subjects"`
	Edges       int `json:"max_dependency_edges"`
	Depth       int `json:"max_path_depth"`
	Paths       int `json:"max_paths"`
	Diagnostics int `json:"max_diagnostics"`
}
type request struct {
	Schema        string     `json:"schema_version"`
	Profile       string     `json:"comparison_profile"`
	ProfileDigest string     `json:"comparison_profile_digest"`
	Analyzer      string     `json:"analyzer_profile"`
	Before        coordinate `json:"before"`
	After         coordinate `json:"after"`
	Scope         scope      `json:"impact_scope"`
	Limits        limits     `json:"limits"`
}
type change struct {
	Identity         string   `json:"identity"`
	Before           *string  `json:"before_identity"`
	After            *string  `json:"after_identity"`
	IdentityRelation string   `json:"identity_relation"`
	Textual          string   `json:"textual_relation"`
	Structural       string   `json:"structural_relation"`
	Semantic         string   `json:"semantic_relation"`
	Reasons          []string `json:"reason_codes"`
}
type dependencyState struct {
	Identity   string   `json:"dependency_identity"`
	Resolution string   `json:"resolution_status"`
	Provenance []string `json:"provenance_digests"`
	Reasons    []string `json:"reason_codes"`
}
type dependencyChange struct {
	Dependent string           `json:"dependent_identity"`
	Rule      string           `json:"rule_id"`
	Version   string           `json:"rule_version"`
	Relation  string           `json:"relation"`
	Before    *dependencyState `json:"before"`
	After     *dependencyState `json:"after"`
}
type pathStep struct {
	Dependent  string `json:"dependent_identity"`
	Dependency string `json:"dependency_identity"`
	Rule       string `json:"rule_id"`
	Version    string `json:"rule_version"`
	Side       string `json:"evidence_side"`
}
type impactPath struct {
	Source   string     `json:"source_identity"`
	Affected string     `json:"affected_identity"`
	Steps    []pathStep `json:"steps"`
}
type result struct {
	Schema        string             `json:"schema_version"`
	Profile       string             `json:"comparison_profile"`
	ProfileDigest string             `json:"comparison_profile_digest"`
	Analyzer      string             `json:"analyzer_profile"`
	RequestDigest string             `json:"request_digest"`
	Before        coordinate         `json:"before"`
	After         coordinate         `json:"after"`
	Scope         scope              `json:"impact_scope"`
	ScopeDigest   string             `json:"impact_scope_digest"`
	Changes       []change           `json:"changes"`
	Dependencies  []dependencyChange `json:"dependencies"`
	Paths         []impactPath       `json:"impact_paths"`
	Completeness  string             `json:"completeness"`
	Reasons       []string           `json:"reason_codes"`
	Context       []string           `json:"context_digests"`
	Diagnostics   []json.RawMessage  `json:"diagnostics"`
}

type transformation struct {
	Status           string `json:"status"`
	SourceProfile    string `json:"source_profile"`
	TargetProfile    string `json:"target_profile"`
	Canonicalization string `json:"canonicalization_profile"`
	SourceDigest     string `json:"source_digest"`
	TargetDigest     string `json:"target_digest"`
	IdentityMap      []struct {
		Before string `json:"before"`
		After  string `json:"after"`
	} `json:"identity_map"`
	Preservation struct {
		Limitations []string `json:"limitations"`
	} `json:"preservation"`
}
type context struct {
	report  *transformation
	digests []string
}
