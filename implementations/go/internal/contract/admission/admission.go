// Package admission owns the complete contract-family semantic rules.
// External payloads are schema-checked before rules inspect their fields.
// Trusted context is supplied explicitly by the consuming service.
package admission

import (
	"io"
	"io/fs"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// Validator holds immutable compiled schemas, catalogs and semantic predicates.
// A caller can share it when its trusted context implementations are safe to share.
type Validator struct {
	low                *validation.Validator
	vocabularies       map[string]any
	profiles           []any
	streams            map[string]any
	relationCatalogs   map[string]any
	relationProfiles   map[string]any
	currentRelations   any
	controlDigests     map[string]string
	informationProfile any
	conceptFamilies    map[string]any
}

type definition struct {
	check                       func(validation.Invocation) error
	contextual, requiresContext bool
}

func invalid() error { return fault.New(fault.InvalidInput, "contract-semantic-mismatch", nil) }
func require(ok bool) error {
	if !ok {
		return invalid()
	}
	return nil
}

func newCatalogOwner() (*Validator, error) {
	source, err := corpus.Open()
	if err != nil {
		return nil, err
	}
	catalog, err := readCatalog(source, "concept-authority/controlled-vocabularies-v1.json")
	if err != nil {
		return nil, err
	}
	profiles, err := readCatalog(source, "profiles/validation/validation-profile-catalog-v1.json")
	if err != nil {
		return nil, err
	}
	owner := &Validator{vocabularies: object(catalog["vocabularies"]), profiles: array(profiles["profiles"]), streams: map[string]any{}}
	for _, id := range []string{termBlake3XofV1, "blake3-xof-participant-v1"} {
		profile, loadErr := readCatalog(source, "profiles/random-stream/"+id+".json")
		if loadErr != nil {
			return nil, loadErr
		}
		if stringAt(profile, termProfileID) != id || !keyed(at(profile, "transforms"), "transform_id") {
			return nil, fault.New(fault.Operational, "contract-catalog-invalid", nil)
		}
		owner.streams[id] = profile
	}
	if err = owner.loadBehavioral(source); err != nil {
		return nil, err
	}
	if err = owner.loadControlProfiles(source); err != nil {
		return nil, err
	}
	families, familyErr := readCatalog(source, "concept-authority/concept-families-v1.json")
	if familyErr != nil {
		return nil, familyErr
	}
	owner.conceptFamilies = object(at(families, "families"))
	owner.informationProfile, err = readCatalog(source, "profiles/participant-information-reconstruction/occurrence-prefix-evidence-v1.json")
	if err != nil {
		return nil, err
	}
	return owner, nil
}

func readCatalog(source fs.FS, path string) (map[string]any, error) {
	file, err := source.Open(path)
	if err != nil {
		return nil, fault.New(fault.Operational, "contract-catalog-invalid", nil)
	}
	const maxBytes = 8 * 1048576
	raw, readErr := io.ReadAll(io.LimitReader(file, maxBytes+1))
	closeErr := file.Close()
	if readErr != nil || closeErr != nil || len(raw) > maxBytes {
		return nil, fault.New(fault.Operational, "contract-catalog-invalid", nil)
	}
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: maxBytes, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, fault.New(fault.Operational, "contract-catalog-invalid", nil)
	}
	return object(value), nil
}

// New constructs a complete registry. It refuses any published invariant that
// has no implemented predicate; missing callbacks never become success.
func New() (*Validator, error) {
	e, err := newCatalogOwner()
	if err != nil {
		return nil, err
	}
	base, err := validation.New(nil)
	if err != nil {
		return nil, err
	}
	rules := make([]validation.Rule, 0, len(base.Keys()))
	for _, key := range base.Keys() {
		rule, ok := e.checker(key.InvariantID)
		if !ok {
			return nil, fault.New(fault.Operational, "contract-rules-incomplete", nil)
		}
		rules = append(rules, validation.Rule{Key: key, Contextual: rule.contextual, RequiresContext: rule.requiresContext, Check: rule.check})
	}
	e.low, err = base.WithRules(rules)
	if err != nil {
		return nil, err
	}
	if err = e.checkCatalogs(); err != nil {
		return nil, err
	}
	return e, nil
}

// Validate checks the complete invariant set, including contextual rules.
func (e *Validator) Validate(id string, data []byte, limits ingress.Limits, context any) (validation.Value, error) {
	data, err := e.prepare(id, data, limits)
	if err != nil {
		return validation.Value{}, err
	}
	admitted, err := e.low.Validate(id, data, limits, context)
	if err != nil {
		return validation.Value{}, err
	}
	if err := e.checkModels(id, data, limits); err != nil {
		return validation.Value{}, err
	}
	return admitted, nil
}

// CheckPortable checks the existing portable entry point's local rules.
// It does not grant contextual authority or full semantic admission.
func (e *Validator) CheckPortable(id string, data []byte, limits ingress.Limits) error {
	data, err := e.prepare(id, data, limits)
	if err != nil {
		return err
	}
	if err := e.low.CheckLocal(id, data, limits); err != nil {
		return err
	}
	if err := e.checkModels(id, data, limits); err != nil {
		return err
	}
	if portableContextRequired(id) {
		return contextRequired()
	}
	return nil
}

func (e *Validator) checker(id string) (definition, bool) {
	rules := e.scalarRules()
	maps.Copy(rules, e.experimentLocalRules())
	maps.Copy(rules, e.artifactRules())
	maps.Copy(rules, e.externalRules())
	maps.Copy(rules, e.profileRules())
	maps.Copy(rules, e.participantLocalRules())
	maps.Copy(rules, e.runJoinRules())
	maps.Copy(rules, e.completenessRules())
	maps.Copy(rules, e.authoringRules())
	maps.Copy(rules, e.temporalRules())
	maps.Copy(rules, e.planningRules())
	maps.Copy(rules, e.selectionRules())
	maps.Copy(rules, e.evidenceOwnerRules())
	maps.Copy(rules, e.executionRules())
	maps.Copy(rules, e.apparatusRules())
	maps.Copy(rules, e.cleanupRules())
	maps.Copy(rules, e.synthesisRules())
	maps.Copy(rules, e.behavioralRules())
	maps.Copy(rules, e.factRules())
	maps.Copy(rules, e.participantInjectRules())
	maps.Copy(rules, e.backendRules())
	maps.Copy(rules, e.comparisonRules())
	maps.Copy(rules, e.opacityRules())
	maps.Copy(rules, e.injectRules())
	maps.Copy(rules, e.decisionRules())
	maps.Copy(rules, e.accountingRules())
	maps.Copy(rules, e.statefulRules())
	maps.Copy(rules, e.envelopeRules())
	maps.Copy(rules, e.descriptionRules())
	maps.Copy(rules, e.experimentJoinRules())
	maps.Copy(rules, e.runProvenanceRules())
	maps.Copy(rules, e.evidenceRelationRules())
	maps.Copy(rules, e.mixedLocalRules())
	maps.Copy(rules, e.controlLocalRules())
	maps.Copy(rules, e.trialPlanRules())
	maps.Copy(rules, e.associatedRules())
	maps.Copy(rules, e.controlContextRules())
	maps.Copy(rules, e.informationRules())
	maps.Copy(rules, e.factorialRules())
	maps.Copy(rules, e.controlOccurrenceRules())
	maps.Copy(rules, e.crossingRules())
	maps.Copy(rules, e.controlResolutionRules())
	maps.Copy(rules, e.flowRules())
	maps.Copy(rules, e.mixedContextRules())
	maps.Copy(rules, e.mixedBackendContextRules())
	maps.Copy(rules, e.mixedStageRules())
	maps.Copy(rules, e.materializationArchiveRules())
	maps.Copy(rules, e.materializationExecutionRules())
	maps.Copy(rules, e.materializationInventoryRules())
	rule, ok := rules[id]
	return rule, ok
}
