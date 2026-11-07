package concept

import (
	"encoding/json"
	"maps"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

// The resolution outcomes of a concept binding. Only ResolvedCurrent is
// active.
const (
	ResolvedCurrent = "resolved-current"
	Unavailable     = "unavailable"
	Stale           = "stale"
	Ambiguous       = "ambiguous"
	Superseded      = "superseded"
	UnknownConcept  = "unknown-concept"
	SubjectNotFound = "subject-not-found"
)

const (
	bindingsContract = "external-concept-bindings-v1"
	bindingDomain    = "external-concept-binding"
	severityError    = "error"
	severityWarning  = "warning"
	supersededStatus = "superseded"
)

// Subject is the exact, digest-pinned coordinate of one RAES subject.
type Subject struct{ SubjectKind, OwningContractID, LifecyclePhase, CanonicalRef, ArtifactDigest string }

// SnapshotTerm is one concept of a scheme snapshot. A current term has no
// successors; a superseded term has at least one.
type SnapshotTerm struct {
	ConceptID, Status   string
	SuccessorConceptIDs []string
}

// SchemeSnapshot is a local, pinned copy of one external scheme revision.
type SchemeSnapshot struct {
	SchemeID, Authority, Revision, SourceLocator, SourceDigest string
	Concepts                                                   []SnapshotTerm
}

// BindingResolution is the outcome of one binding. ResolvedConceptID is set
// for a resolved or superseded concept.
type BindingResolution struct {
	BindingID, Outcome string
	Active             bool
	ResolvedConceptID  *string
	Diagnostics        []diagnostic.Diagnostic
}

// ResolutionOutcome reports each binding of one binding set in ID order.
type ResolutionOutcome struct {
	BindingSetID string
	Results      []BindingResolution
}

// Admitted reports whether the set has a result and every result is active.
func (result ResolutionOutcome) Admitted() bool {
	return len(result.Results) > 0 && !slices.ContainsFunc(result.Results, func(r BindingResolution) bool { return !r.Active })
}

type subjectWire struct {
	SubjectKind      string `json:"subject_kind"`
	OwningContractID string `json:"owning_contract_id"`
	LifecyclePhase   string `json:"lifecycle_phase"`
	CanonicalRef     string `json:"canonical_ref"`
	ArtifactDigest   string `json:"artifact_digest"`
}

type schemeWire struct {
	SchemeID      string  `json:"scheme_id"`
	Authority     string  `json:"authority"`
	Revision      string  `json:"revision"`
	ConceptID     string  `json:"concept_id"`
	SourceLocator *string `json:"source_locator"`
	SourceDigest  *string `json:"source_digest"`
}

type bindingsWire struct {
	BindingSetID string `json:"binding_set_id"`
	Bindings     map[string]struct {
		Subject subjectWire `json:"subject"`
		Scheme  schemeWire  `json:"scheme"`
	} `json:"bindings"`
}

func invalidInput() error {
	return fault.New(fault.InvalidInput, "external-concept-input-invalid", nil)
}

// AdmitBindings resolves an admitted external-concept-bindings-v1 document
// against the supplied subjects and scheme snapshots. It refuses a document
// that is not admitted, an invalid subject and an invalid snapshot with an
// InvalidInput fault.
func (a *Authority) AdmitBindings(subjects []Subject, bindings validation.Value, snapshots []SchemeSnapshot) (ResolutionOutcome, error) {
	if bindings.ContractID() != bindingsContract {
		return ResolutionOutcome{}, invalidInput()
	}
	var document bindingsWire
	if json.Unmarshal(bindings.JSON(), &document) != nil {
		return ResolutionOutcome{}, invalidInput()
	}
	if err := a.checkSubjects(subjects); err != nil {
		return ResolutionOutcome{}, err
	}
	for _, snapshot := range snapshots {
		if err := checkSnapshot(snapshot); err != nil {
			return ResolutionOutcome{}, err
		}
	}
	outcome := ResolutionOutcome{BindingSetID: document.BindingSetID}
	for position, id := range slices.Sorted(maps.Keys(document.Bindings)) {
		binding := document.Bindings[id]
		address := "/bindings/" + strconv.Itoa(position)
		result, settled := resolveSubject(id, binding.Subject, subjects, address+"/subject")
		if !settled {
			result = resolveScheme(id, binding.Scheme, snapshots, address+"/scheme")
		}
		outcome.Results = append(outcome.Results, result)
	}
	return outcome, nil
}

// checkSubjects applies the published subject definition to each subject.
func (a *Authority) checkSubjects(subjects []Subject) error {
	for _, subject := range subjects {
		data, err := json.Marshal(subjectWire(subject))
		if err != nil {
			return invalidInput()
		}
		if _, err := a.schemas.DecodeObjectFragment(bindingsContract, "#/$defs/ExternalConceptSubjectModel", data, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 4}); err != nil {
			return invalidInput()
		}
	}
	return nil
}

// checkSnapshot applies the reference snapshot rules: non-empty identity, a
// prefixed digest, an inert absolute locator, at least one concept and
// consistent successors.
func checkSnapshot(s SchemeSnapshot) error {
	if s.SchemeID == "" || s.Authority == "" || s.Revision == "" || s.SourceLocator == "" || !digest.Valid(s.SourceDigest) || len(s.Concepts) == 0 {
		return invalidInput()
	}
	if urisafety.Check(s.SourceLocator, urisafety.Options{ForbiddenSchemes: []string{"file", "data"}, ForbidFragment: true}) != nil {
		return invalidInput()
	}
	for _, term := range s.Concepts {
		if err := checkTerm(term); err != nil {
			return err
		}
	}
	return nil
}

func checkTerm(term SnapshotTerm) error {
	if term.ConceptID == "" || slices.Contains(term.SuccessorConceptIDs, "") {
		return invalidInput()
	}
	successors := len(term.SuccessorConceptIDs)
	if term.Status == currentStatus && successors == 0 {
		return nil
	}
	if term.Status != supersededStatus || successors == 0 || len(slices.Compact(slices.Sorted(slices.Values(term.SuccessorConceptIDs)))) != successors {
		return invalidInput()
	}
	return nil
}

func result(id, outcome, address, message string, resolved *string) BindingResolution {
	r := BindingResolution{BindingID: id, Outcome: outcome, Active: outcome == ResolvedCurrent, ResolvedConceptID: resolved}
	if r.Active {
		return r
	}
	severity := severityError
	if outcome == Unavailable {
		severity = severityWarning
	}
	r.Diagnostics = []diagnostic.Diagnostic{{Code: "external-concept." + outcome, Severity: severity, Message: message, Domain: bindingDomain, Address: address}}
	return r
}

// resolveSubject reports a settled result unless exactly one supplied
// subject equals the asserted coordinate.
func resolveSubject(id string, asserted subjectWire, subjects []Subject, address string) (BindingResolution, bool) {
	want := Subject(asserted)
	exact, sameCoordinate := 0, false
	for _, candidate := range subjects {
		if candidate == want {
			exact++
		}
		candidate.ArtifactDigest = want.ArtifactDigest
		sameCoordinate = sameCoordinate || candidate == want
	}
	if exact == 1 {
		return BindingResolution{}, false
	}
	if exact > 1 {
		return result(id, Ambiguous, address, "the exact RAES subject coordinate resolves to multiple supplied candidates", nil), true
	}
	if sameCoordinate {
		return result(id, Stale, address, "the supplied RAES subject digest does not match the asserted artifact digest", nil), true
	}
	return result(id, SubjectNotFound, address, "the exact RAES subject coordinate is unavailable in the supplied local subject index", nil), true
}

func resolveScheme(id string, scheme schemeWire, snapshots []SchemeSnapshot, address string) BindingResolution {
	identity, exact := 0, []SchemeSnapshot(nil)
	for _, snapshot := range snapshots {
		if snapshot.SchemeID != scheme.SchemeID || snapshot.Authority != scheme.Authority {
			continue
		}
		identity++
		if snapshotMatches(snapshot, scheme) {
			exact = append(exact, snapshot)
		}
	}
	if identity == 0 {
		return result(id, Unavailable, address, "no matching local scheme snapshot was supplied; the assertion remains inactive", nil)
	}
	if len(exact) == 0 {
		return result(id, Stale, address, "the supplied scheme snapshot conflicts with the asserted revision or digest", nil)
	}
	if len(exact) > 1 {
		return result(id, Ambiguous, address, "the exact scheme coordinate resolves to multiple supplied snapshots", nil)
	}
	return resolveConcept(id, scheme.ConceptID, exact[0], address)
}

// snapshotMatches compares the exact revision and each asserted source pin.
// Digests compare without ASCII case.
func snapshotMatches(snapshot SchemeSnapshot, scheme schemeWire) bool {
	if snapshot.Revision != scheme.Revision {
		return false
	}
	if scheme.SourceLocator != nil && snapshot.SourceLocator != *scheme.SourceLocator {
		return false
	}
	return scheme.SourceDigest == nil || strings.EqualFold(snapshot.SourceDigest, *scheme.SourceDigest)
}

func resolveConcept(id, concept string, snapshot SchemeSnapshot, address string) BindingResolution {
	var terms []SnapshotTerm
	for _, term := range snapshot.Concepts {
		if term.ConceptID == concept {
			terms = append(terms, term)
		}
	}
	if len(terms) == 0 {
		return result(id, UnknownConcept, address, "the asserted concept is absent from the exact supplied scheme revision", nil)
	}
	if len(terms) > 1 {
		return result(id, Ambiguous, address, "the asserted concept resolves to multiple candidates in the exact supplied scheme revision", nil)
	}
	if terms[0].Status == supersededStatus {
		return result(id, Superseded, address, "the original concept is superseded; automatic successor rewriting is forbidden", &concept)
	}
	return result(id, ResolvedCurrent, address, "", &concept)
}
