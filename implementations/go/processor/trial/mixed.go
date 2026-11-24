package trial

import (
	"context"
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const mixedProfileContract = "mixed-participant-composition-profile-v1"

type mixedProfile struct {
	ID         string    `json:"profile_id"`
	Revision   string    `json:"profile_revision"`
	Digest     string    `json:"profile_digest"`
	Scenario   reference `json:"scenario_snapshot_ref"`
	Components map[string]struct {
		Manifest reference       `json:"manifest_ref"`
		Envelope json.RawMessage `json:"realization_envelope"`
	} `json:"components"`
	Allocations map[string]struct {
		Features []json.RawMessage `json:"feature_requirements"`
	} `json:"allocations"`
	Edges       map[string]mixedEvidenceCarrier `json:"edges"`
	Phases      map[string]mixedEvidenceCarrier `json:"phases"`
	Transitions map[string]mixedEvidenceCarrier `json:"transitions"`
	Nested      map[string]string               `json:"nested_profile_refs"`
}
type mixedEvidenceCarrier struct {
	Evidence []json.RawMessage `json:"evidence_bindings"`
}
type mixedAssignment struct {
	Profile      reference                      `json:"profile_ref"`
	Participants []participantManifestReference `json:"participant_manifest_refs"`
	Source       *mixedSource                   `json:"source_trial"`
}
type mixedSource struct {
	PlanID      string `json:"plan_id"`
	PlanDigest  string `json:"plan_digest"`
	EntryID     string `json:"plan_entry_id"`
	EntryDigest string `json:"entry_digest"`
	RunID       string `json:"run_id"`
}
type mixedAuthority struct {
	profiles  []mixedProfile
	manifests map[ApparatusManifestKey]admission.ApparatusManifest
	backends  map[ApparatusManifestKey]binding.BackendManifestV2
	envelopes map[ApparatusManifestKey]binding.RealizationEnvelopeV1
}
type mixedTrialContext struct {
	admission.MixedCompositionContext

	snapshot admission.MixedCompositionSnapshot
}

func (c mixedTrialContext) MixedCompositionSnapshot() admission.MixedCompositionSnapshot {
	return c.snapshot
}
func compositionRefusal(code, message string) error {
	return refuse(code, "/realization_assignments", message)
}
func mixedContextRefusal() error {
	return compositionRefusal("composition-context-rejected", "composition profile failed trusted contextual admission")
}

func validateMixedPins(request Request, input compilationInputs) (map[string]mixedProfile, error) {
	supplied := map[string]mixedProfile{}
	for _, id := range slices.Sorted(maps.Keys(request.MixedProfiles)) {
		value := request.MixedProfiles[id]
		if value.ContractID() != mixedProfileContract || input.owner.CheckModelFragment(mixedProfileContract, "#", value.JSON(), trialIngress()) != nil {
			return nil, refuse("mixed-profile-invalid", "/input_refs/mixed_composition_profile_refs", "a supplied mixed composition profile failed closed reconstruction")
		}
		var profile mixedProfile
		if decode(value.JSON(), &profile) != nil {
			return nil, trialInvalid()
		}
		supplied[id] = profile
	}
	mismatch := len(supplied) != len(input.refs.Mixed)
	for _, ref := range input.refs.Mixed {
		p, ok := supplied[ref.ID]
		mismatch = mismatch || !ok || p.ID != ref.ID || p.Revision != text(ref.Version) || p.Digest != text(ref.Digest)
	}
	for id, p := range supplied {
		mismatch = mismatch || id != p.ID
	}
	if mismatch {
		return nil, refuse("mixed-profile-input-mismatch", "/input_refs/mixed_composition_profile_refs", "mixed composition profile references do not resolve exactly to the supplied profiles")
	}
	return supplied, nil
}
func validateMixedAssignments(request Request, input compilationInputs, coordinates []coordinate, profiles map[string]mixedProfile) error {
	if len(request.RealizationAssignments) == 0 && len(profiles) == 0 && len(input.refs.Mixed) == 0 {
		return nil
	}
	if len(request.RealizationAssignments) != len(coordinates) {
		return compositionRefusal("realization-assignment-incomplete", "mixed composition realization assignments must cover every canonical coordinate exactly once")
	}
	var apparatus apparatusBinding
	if decode(input.apparatusJSON, &apparatus) != nil {
		return trialInvalid()
	}
	expected := canonicalParticipants(apparatus.Participants)
	for _, coordinate := range coordinates {
		key, err := canonical(coordinate.projection())
		if err != nil {
			return err
		}
		fragment, present := request.RealizationAssignments[string(key)]
		if !present {
			return compositionRefusal("realization-assignment-incomplete", "mixed composition realization assignments must cover every canonical coordinate exactly once")
		}
		if err = validateMixedAssignment(input.owner, fragment, profiles, expected); err != nil {
			return err
		}
	}
	return nil
}
func validateMixedAssignment(owner *admission.Validator, fragment admission.Fragment, profiles map[string]mixedProfile, expected []string) error {
	_, assignment, err := mixedBinding(owner, fragment)
	if err != nil {
		return err
	}
	profile, ok := profiles[assignment.Profile.ID]
	if !ok || profile.Revision != text(assignment.Profile.Version) || profile.Digest != text(assignment.Profile.Digest) {
		return compositionRefusal("realization-assignment-profile-mismatch", "a realization assignment does not resolve to its exact supplied composition profile")
	}
	actual := canonicalParticipants(assignment.Participants)
	if !slices.Equal(actual, expected) {
		return compositionRefusal("realization-assignment-participant-manifest-mismatch", "a realization assignment does not bind the exact selected participant manifest authority")
	}
	return nil
}
func participantAuthorityKey(ref participantManifestReference) string {
	return strings.Join([]string{ref.Address, ref.Name, ref.Version, ref.ManifestVersion, ref.ManifestDigest}, "\x00")
}
func canonicalParticipants(refs []participantManifestReference) []string {
	result := make([]string, len(refs))
	for i, ref := range refs {
		result[i] = participantAuthorityKey(ref)
	}
	slices.Sort(result)
	return slices.Compact(result)
}
func mixedBinding(owner *admission.Validator, fragment admission.Fragment) (json.RawMessage, mixedAssignment, error) {
	var assignment mixedAssignment
	if admission.CheckFragment(fragment, admission.AdmittedMixedCompositionBinding) != nil {
		return nil, assignment, trialInvalid()
	}
	raw, err := encoded(fragment.Document())
	if err != nil {
		return nil, assignment, err
	}
	if owner.CheckModelFragment("admitted-trial-plan-v1", "#/$defs/AdmittedMixedCompositionBindingModel", raw, trialIngress()) != nil || decode(raw, &assignment) != nil {
		return nil, assignment, trialInvalid()
	}
	var root map[string]json.RawMessage
	if decode(raw, &root) != nil {
		return nil, assignment, trialInvalid()
	}
	var participants []json.RawMessage
	if !isNull(root["participant_manifest_refs"]) && decode(root["participant_manifest_refs"], &participants) != nil {
		return nil, assignment, trialInvalid()
	}
	slices.SortFunc(participants, func(a, b json.RawMessage) int {
		var x, y participantManifestReference
		_ = decode(a, &x)
		_ = decode(b, &y)
		return strings.Compare(participantAuthorityKey(x), participantAuthorityKey(y))
	})
	if len(participants) > 0 {
		root["participant_manifest_refs"], err = encoded(participants)
		if err != nil {
			return nil, assignment, err
		}
	} else {
		delete(root, "participant_manifest_refs")
	}
	raw, err = encoded(root)
	return raw, assignment, err
}

type mixedAuthorityCompiler struct {
	request   Request
	input     compilationInputs
	admitted  map[string]string
	totalWork int
}

func prepareMixedAuthority(ctx context.Context, request Request, input compilationInputs, profiles map[string]mixedProfile) (map[string]mixedAuthority, error) {
	compiler := mixedAuthorityCompiler{request: request, input: input, admitted: map[string]string{}}
	result := map[string]mixedAuthority{}
	for _, id := range slices.Sorted(maps.Keys(profiles)) {
		authority, err := compiler.compose(ctx, id, profiles[id])
		if err != nil {
			return nil, err
		}
		result[id] = authority
	}
	return result, nil
}
func (c *mixedAuthorityCompiler) compose(ctx context.Context, id string, profile mixedProfile) (mixedAuthority, error) {
	authority := mixedAuthority{manifests: map[ApparatusManifestKey]admission.ApparatusManifest{}, backends: map[ApparatusManifestKey]binding.BackendManifestV2{}, envelopes: map[ApparatusManifestKey]binding.RealizationEnvelopeV1{}}
	snapshot, err := c.snapshot(ctx, id)
	if err != nil {
		return authority, err
	}
	closure, err := mixedClosure(c.request, c.input.owner, profile, snapshot)
	if err != nil {
		return authority, err
	}
	authority.profiles = closure
	for _, member := range closure {
		if err = c.member(member, snapshot, &authority); err != nil {
			return authority, err
		}
	}
	return authority, nil
}
func (c *mixedAuthorityCompiler) snapshot(ctx context.Context, id string) (admission.MixedCompositionSnapshot, error) {
	owner, ok := c.request.MixedProfileContexts[id]
	if !ok || owner == nil {
		return admission.MixedCompositionSnapshot{}, compositionRefusal("composition-context-missing", "composition profile trusted resolution context is missing")
	}
	snapshot, err := installedTrialOwner(ctx, func() (admission.MixedCompositionSnapshot, error) { return owner.MixedCompositionSnapshot(), nil })
	if err != nil {
		return snapshot, err
	}
	snapshot.TrialAdmission = true
	_, err = c.input.owner.Validate(mixedProfileContract, c.request.MixedProfiles[id].JSON(), trialIngress(), mixedTrialContext{owner, snapshot})
	if err != nil {
		return snapshot, mixedContextRefusal()
	}
	return snapshot, nil
}
func (c *mixedAuthorityCompiler) member(profile mixedProfile, snapshot admission.MixedCompositionSnapshot, authority *mixedAuthority) error {
	if old, present := c.admitted[profile.ID]; present && old != profile.Digest {
		return compositionRefusal("composition-profile-identity-conflict", "one composition profile identity resolves to conflicting payloads")
	}
	if _, present := c.admitted[profile.ID]; !present {
		c.admitted[profile.ID] = profile.Digest
		c.totalWork += mixedProfileWork(profile)
	}
	if len(c.admitted) > c.request.Limits.MaxMixedProfiles {
		return compositionRefusal("mixed-profile-limit-exceeded", "reachable mixed composition profiles exceed the compilation limit")
	}
	if c.totalWork > c.request.Limits.MaxMixedContextWork {
		return compositionRefusal("mixed-context-work-limit-exceeded", "reachable mixed composition contextual work exceeds the compilation limit")
	}
	required, present := snapshot.ResourceRefs[profile.ID]
	if !present {
		return compositionRefusal("composition-resource-coverage-unresolved", "composition cleanup and isolation resource coverage is unresolved")
	}
	if err := mixedResourceCoverage(c.input.authority.Cleanup, required); err != nil {
		return err
	}
	return admitMixedComponents(c.request, c.input, profile, authority)
}
func mixedProfileWork(p mixedProfile) int {
	work := len(p.Components) + len(p.Allocations) + len(p.Edges) + len(p.Phases) + len(p.Transitions) + len(p.Nested)
	for _, a := range p.Allocations {
		work += len(a.Features)
	}
	for _, set := range []map[string]mixedEvidenceCarrier{p.Edges, p.Phases, p.Transitions} {
		for _, v := range set {
			work += len(v.Evidence)
		}
	}
	return work
}

type mixedClosureWalk struct {
	request  Request
	owner    *admission.Validator
	snapshot admission.MixedCompositionSnapshot
	visited  map[string]bool
	work     int
	closure  []mixedProfile
}

func mixedClosure(request Request, owner *admission.Validator, root mixedProfile, snapshot admission.MixedCompositionSnapshot) ([]mixedProfile, error) {
	walk := mixedClosureWalk{request: request, owner: owner, snapshot: snapshot, visited: map[string]bool{}}
	if err := walk.visit(root, request.MixedProfiles[root.ID].JSON()); err != nil {
		return nil, err
	}
	return walk.closure, nil
}
func (w *mixedClosureWalk) visit(profile mixedProfile, raw []byte) error {
	w.work++
	if w.work > w.request.MixedCompositionLimits.MaxContextWork {
		return mixedContextRefusal()
	}
	if w.visited[profile.ID] {
		return nil
	}
	w.visited[profile.ID] = true
	if len(w.visited) > w.request.MixedCompositionLimits.MaxNestedProfiles {
		return mixedContextRefusal()
	}
	if err := mixedProfileLimits(raw, profile, w.request.MixedCompositionLimits); err != nil {
		return err
	}
	w.work += mixedProfileWork(profile) - len(profile.Phases)
	if w.work > w.request.MixedCompositionLimits.MaxContextWork {
		return mixedContextRefusal()
	}
	w.closure = append(w.closure, profile)
	return w.nested(profile)
}
func (w *mixedClosureWalk) nested(profile mixedProfile) error {
	for _, id := range slices.Sorted(maps.Keys(profile.Nested)) {
		raw, ok := w.snapshot.NestedProfiles[id]
		if !ok || w.owner.CheckModelFragment(mixedProfileContract, "#", raw, trialIngress()) != nil {
			return mixedContextRefusal()
		}
		var child mixedProfile
		if decode(raw, &child) != nil || child.ID != id || child.Digest != profile.Nested[id] {
			return mixedContextRefusal()
		}
		if err := w.visit(child, raw); err != nil {
			return err
		}
	}
	return nil
}
func mixedProfileLimits(raw []byte, p mixedProfile, limits MixedCompositionLimits) error {
	if len(raw) > limits.MaxSourceBytes {
		return mixedContextRefusal()
	}
	for _, v := range [][2]int{{len(p.Components), limits.MaxComponents}, {len(p.Allocations), limits.MaxAllocations}, {len(p.Edges), limits.MaxEdges}, {len(p.Phases), limits.MaxPhases}, {len(p.Transitions), limits.MaxTransitions}, {len(p.Nested), limits.MaxNestedProfiles}} {
		if v[0] > v[1] {
			return mixedContextRefusal()
		}
	}
	tree, err := ingress.Parse(raw, ingress.Limits{MaxBytes: limits.MaxSourceBytes, MaxDepth: limits.MaxJSONDepth}, ingress.Object)
	if err != nil {
		return mixedContextRefusal()
	}
	remaining := limits.MaxJSONNodes
	if !countMixedJSON(tree, &remaining) {
		return mixedContextRefusal()
	}
	return nil
}
func countMixedJSON(node any, remaining *int) bool {
	*remaining--
	if *remaining < 0 {
		return false
	}
	switch children := node.(type) {
	case map[string]any:
		for _, child := range children {
			if !countMixedJSON(child, remaining) {
				return false
			}
		}
	case []any:
		for _, child := range children {
			if !countMixedJSON(child, remaining) {
				return false
			}
		}
	}
	return true
}
func mixedResourceCoverage(raw json.RawMessage, required []string) error {
	var cleanup struct {
		Boundaries map[string]struct {
			Resources []string `json:"resource_refs"`
		} `json:"resource_boundaries"`
	}
	if decode(raw, &cleanup) != nil {
		return trialInvalid()
	}
	covered := map[string]bool{}
	for _, boundary := range cleanup.Boundaries {
		for _, ref := range boundary.Resources {
			covered[ref] = true
		}
	}
	for _, ref := range required {
		if !covered[ref] {
			return refuse("composition-resource-coverage-missing", "/execution_authority/cleanup", "composition cleanup omits a resource reachable in an admitted phase")
		}
	}
	return nil
}
func validateMixedSelected(request Request, input compilationInputs, assignment mixedAssignment, selected sdl.InstantiatedScenario) error {
	digest, err := sdl.CanonicalDigest(selected)
	if err != nil {
		return err
	}
	for _, p := range input.mixed[assignment.Profile.ID].profiles {
		if text(p.Scenario.Digest) != digest {
			return compositionRefusal("composition-scenario-snapshot-mismatch", "a reachable composition profile scenario snapshot does not match the selected scenario")
		}
	}
	if assignment.Source != nil {
		return validateMixedSource(request, input, *assignment.Source, selected)
	}
	return nil
}

func canonicalMixedRefs(raw json.RawMessage) (json.RawMessage, error) {
	var refs map[string]json.RawMessage
	if decode(raw, &refs) != nil {
		return nil, trialInvalid()
	}
	var profiles []json.RawMessage
	if decode(refs["mixed_composition_profile_refs"], &profiles) != nil {
		return nil, trialInvalid()
	}
	slices.SortFunc(profiles, func(a, b json.RawMessage) int {
		var left, right reference
		_ = decode(a, &left)
		_ = decode(b, &right)
		for _, pair := range [][2]string{{left.ID, right.ID}, {text(left.Version), text(right.Version)}, {text(left.Digest), text(right.Digest)}} {
			if c := strings.Compare(pair[0], pair[1]); c != 0 {
				return c
			}
		}
		return 0
	})
	var err error
	refs["mixed_composition_profile_refs"], err = encoded(profiles)
	if err != nil {
		return nil, err
	}
	return encoded(refs)
}
