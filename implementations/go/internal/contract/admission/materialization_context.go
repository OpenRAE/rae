package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// MaterializationCompileRequest addresses the existing SDL semantic/compiler
// owner. Source is the exact document; ContractID fixes the required SDL phase.
type MaterializationCompileRequest struct {
	ContractID  string
	Source      []byte
	Plan        validation.Value
	Predecessor []byte
}

// MaterializationCompilation is typed phase data, never an admission decision.
// Document preserves supplied fields; FullDocument includes model defaults.
// Resources use the published SnapshotEntryModel with status "ready". The
// compiler retains plan/predecessor profile and regeneration scope metadata.
// NodeCollection is the original PreparedNodeCollectionAuthority. NodeConcerns
// contains registered value-free provenance rows per compiled resource address.
// PreparedNodeRequirements contains that owner's derived compiled requirements.
// OrdinarySelections maps registered SDL pointers to original concern field paths.
// NodePresence holds typed realizable child names per node and relative SDL path.
// These are complete owner projections, independently derived from the source;
// candidate reports cannot supply, prune or widen them.
type MaterializationCompilation struct {
	SourceSHA256             string
	Document, FullDocument   []byte
	Resources                [][]byte
	CollectionIdentities     map[string][]string
	RealizationRequirements  [][]byte
	NodeCollection           []byte
	NodeConcerns             map[string][][]byte
	PreparedNodeRequirements map[string][][]byte
	OrdinarySelections       map[string]string
	NodePresence             map[string]map[string][]string
}

// MaterializationNodeProjection addresses the registered node comparison owner.
// Normalization must retain native identities, supplied concerns and protected
// value commitments. The caller supplies original realization requirements.
type MaterializationNodeProjection struct {
	Name         string
	Node         json.RawMessage
	Requirements []json.RawMessage
}

// MaterializationCompiler reuses the configured SDL and node projection owners.
// It must perform ordinary closed-phase SDL semantic admission and compilation.
// It does not decide any materialization, archive or inventory admission rule.
type MaterializationCompiler interface {
	CompileMaterialization(request MaterializationCompileRequest) (MaterializationCompilation, error)
	NormalizeMaterializationNode(request MaterializationNodeProjection) (json.RawMessage, error)
}

// MaterializationArchiveContext supplies protected original bytes and the
// established SDL owner. The archive validator never opens a path or locator.
type MaterializationArchiveContext interface {
	MaterializationCompiler
	ArchivedMaterializationSDL() []byte
}

type materializationCompiled struct {
	document, full     any
	resources          map[string]any
	identities         map[string][]string
	requirements       []json.RawMessage
	collection         any
	concerns, prepared map[string][]json.RawMessage
	ordinary           map[string]string
	presence           map[string]map[string][]string
}

// MaterializationExecutionSnapshot carries the independently admitted execution.
// Predecessor is the native RuntimeSnapshot JSON projection (no schema_version).
// Plan is the completed published provisioning, orchestration or evaluation
// model projection with its exclude-none serializer. Manifest is the complete
// published backend manifest projection. Neither is a candidate-supplied claim.
type MaterializationExecutionSnapshot struct {
	Plan, Manifest, Actual validation.Value
	Predecessor            []byte
	Submission             []byte
}

// MaterializationExecutionContext supplies execution authority and phase owners.
// Its submission must be the exact bytes being admitted, never a reconstructed
// candidate whose defaults or original source identity have changed.
type MaterializationExecutionContext interface {
	MaterializationCompiler
	MaterializationExecutionSnapshot() MaterializationExecutionSnapshot
}

// MaterializationInventoryContext supplies the actual configured envelope and
// protected bytes for the retained archive record selected by this library.
// RetainedMaterializationSDL must fail if those bytes cannot be authenticated.
type MaterializationInventoryContext interface {
	MaterializationExecutionContext
	MaterializationEnvelope() validation.Value
	RetainedMaterializationSDL(record json.RawMessage) ([]byte, error)
}
