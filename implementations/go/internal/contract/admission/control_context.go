package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// ControlSnapshot is an owner-supplied immutable view of control authority.
// Lifecycle keys are asset ID, asset version and cut reference, respectively.
type ControlSnapshot struct {
	ScopeRef, RunID, ParticipantAddress, EpisodeID, AudienceScopeRef string
	EpisodeGeneration                                                json.Number
	RecordCut                                                        json.RawMessage
	Lifecycle                                                        map[[3]string]string
	Roles                                                            map[string][]string
}

// ControlAuthorityRequest binds each host authorization to its complete scope.
type ControlAuthorityRequest struct {
	Operation, AuthorityRef, ActorRef string
	Snapshot                          ControlSnapshot
	AssetReference, StateCut          json.RawMessage
}

// ControlContextAgreementContext supplies authority facts, without acquiring
// content or mutating the lifecycle. Resolver errors remain operational errors.
type ControlContextAgreementContext interface {
	ControlSnapshot() ControlSnapshot
	ControlAssets() [][]byte
	ControlSelections() [][]byte
	ControlSurfaces() [][]byte
	ControlViews() [][]byte
	AuthorizeControl(request ControlAuthorityRequest) (bool, error)
	ControlCutPrecedes(earlier, later json.RawMessage) (bool, error)
}

// ControlContextContentContext adds the concrete content binding for an asset.
type ControlContextContentContext interface {
	AssociatedArtifactsContext
	ControlContentManifest() []byte
}

type controlAgreement struct {
	context                             ControlContextAgreementContext
	snapshot                            ControlSnapshot
	cut                                 any
	assets, selections, surfaces, views map[string]any
}

func (e *Validator) controlContextRules() map[string]definition {
	return map[string]definition{"control-context-trusted-agreement": {check: e.controlContextAgreement, contextual: true, requiresContext: true}}
}

func (e *Validator) controlContextAgreement(i validation.Invocation) error {
	context, ok := i.Context.(ControlContextAgreementContext)
	if !ok {
		return contextRequired()
	}
	state, err := e.controlAgreementState(context)
	if err != nil {
		return err
	}
	v, err := e.defaulted(i.Key.ContractID, i.Instance)
	if err != nil {
		return err
	}
	controlContextDefaults(v)
	switch i.Key.ContractID {
	case termParticipantControlContextAssetV1:
		return e.controlAssetAgreement(v, state, i.Context)
	case termParticipantControlContextChangeV1:
		return state.change(v)
	case termParticipantControlContextRecordV1:
		return state.record(v)
	default:
		return invalid()
	}
}

func (e *Validator) controlAgreementState(context ControlContextAgreementContext) (*controlAgreement, error) {
	snapshot := context.ControlSnapshot()
	if len(snapshot.Lifecycle) > 100000 || len(snapshot.Roles) > 100000 {
		return nil, invalid()
	}
	if snapshot.ScopeRef == "" || snapshot.RunID == "" || snapshot.ParticipantAddress == "" || snapshot.EpisodeID == "" || snapshot.AudienceScopeRef == "" {
		return nil, invalid()
	}
	generation, ok := number(snapshot.EpisodeGeneration)
	if !ok || generation.Sign() < 0 || !generation.IsInt() {
		return nil, invalid()
	}
	cut, err := e.controlCut(snapshot.RecordCut)
	if err != nil {
		return nil, err
	}
	state := &controlAgreement{context: context, snapshot: snapshot, cut: cut}
	state.assets, err = e.controlDocumentMap(termParticipantControlContextAssetV1, context.ControlAssets(), "asset_id", "asset_version")
	if err != nil {
		return nil, err
	}
	state.selections, err = e.controlDocumentMap(termParticipantControlContextRecordV1, context.ControlSelections(), "selection_ref")
	if err != nil {
		return nil, err
	}
	state.surfaces, err = e.controlDocumentMap(termParticipantDecisionSurfaceV2, context.ControlSurfaces(), "participant_view", termSurfaceID)
	if err != nil {
		return nil, err
	}
	state.views, err = e.controlDocumentMap(termParticipantContextViewV1, context.ControlViews(), "view_ref")
	if err != nil {
		return nil, err
	}
	return state, nil
}

func (e *Validator) controlDocumentMap(id string, raw [][]byte, fields ...string) (map[string]any, error) {
	documents, err := e.experimentDocuments(id, raw)
	if err != nil {
		return nil, err
	}
	result := map[string]any{}
	for _, document := range documents {
		v, err := e.defaulted(id, document)
		if err != nil {
			return nil, err
		}
		controlContextDefaults(v)
		key := stringAt(v, fields[0])
		if id == termParticipantControlContextAssetV1 && len(fields) > 1 {
			key = join(key, stringAt(v, fields[1]))
		}
		if id == termParticipantDecisionSurfaceV2 {
			key = stringAt(v, fields...)
		}
		if result[key] != nil {
			return nil, invalid()
		}
		result[key] = v
	}
	return result, nil
}

func (e *Validator) controlCut(raw []byte) (any, error) {
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 32}, ingress.Object)
	if err != nil {
		return nil, invalid()
	}
	name := map[string]string{termSequencePrefix: "ParticipantDecisionSurfaceSequenceCutModel", "causal_frontier": "ParticipantDecisionSurfaceCausalCutModel"}[stringAt(value, "cut_kind")]
	if name == "" {
		return nil, invalid()
	}
	value, err = e.low.DecodeObjectFragment(termParticipantControlContextRecordV1, "#/$defs/"+name, raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 32})
	if err != nil {
		return nil, err
	}
	if err := decisionCut(value); err != nil {
		return nil, err
	}
	if stringAt(value, "cut_kind") == termSequencePrefix && at(value, "predecessor_event_refs") == nil {
		object(value)["predecessor_event_refs"] = []any{}
	}
	return value, nil
}

func (s *controlAgreement) resolve(ref any) any {
	asset := s.assets[join(stringAt(ref, "asset_id"), stringAt(ref, "asset_version"))]
	if asset == nil {
		return nil
	}
	digest, err := jsonDigest(asset)
	if err != nil || stringAt(ref, "asset_digest") != digest {
		return nil
	}
	return asset
}

func (s *controlAgreement) lifecycle(ref, cut any) string {
	return s.snapshot.Lifecycle[[3]string{stringAt(ref, "asset_id"), stringAt(ref, "asset_version"), stringAt(cut, "cut_ref")}]
}

func (s *controlAgreement) ordered(earlier, later any) error {
	if equal(earlier, later) {
		return nil
	}
	left, err := json.Marshal(earlier)
	if err != nil {
		return invalid()
	}
	right, err := json.Marshal(later)
	if err != nil {
		return invalid()
	}
	ok, err := s.context.ControlCutPrecedes(left, right)
	return controlAuthorityResult(ok, err)
}

func controlAuthorityResult(ok bool, err error) error {
	if err != nil {
		return fault.New(fault.Operational, "control-authority-unavailable", nil)
	}
	return require(ok)
}

func (s *controlAgreement) authorized(operation, authority, actor string, ref, cut any) error {
	assetRaw, err := json.Marshal(ref)
	if err != nil {
		return invalid()
	}
	cutRaw, err := json.Marshal(cut)
	if err != nil {
		return invalid()
	}
	ok, err := s.context.AuthorizeControl(ControlAuthorityRequest{operation, authority, actor, s.snapshot, assetRaw, cutRaw})
	return controlAuthorityResult(ok, err)
}

func (e *Validator) controlAssetAgreement(v any, s *controlAgreement, trusted any) error {
	digest, err := jsonDigest(v)
	if err != nil {
		return err
	}
	ref := map[string]any{"asset_id": at(v, "asset_id"), "asset_version": at(v, "asset_version"), "asset_digest": digest}
	if !equal(s.resolve(ref), v) {
		return invalid()
	}
	context, ok := trusted.(ControlContextContentContext)
	if !ok {
		return contextRequired()
	}
	manifest, err := e.contextDocument(termAssociatedArtifactManifestV1, context.ControlContentManifest())
	if err != nil {
		return err
	}
	manifest, err = e.defaulted(termAssociatedArtifactManifestV1, manifest)
	if err != nil {
		return err
	}
	if !equal(at(manifest, "artifacts", stringAt(v, "content", termArtifactID)), at(v, "content")) {
		return invalid()
	}
	return e.associatedArtifacts(validation.Invocation{Instance: manifest, Context: context})
}
