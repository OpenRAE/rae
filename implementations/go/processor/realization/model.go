package realization

import (
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// Descriptor identifies one native realization concern and its authored and payload paths.
type Descriptor struct {
	Kind                                      string
	Document                                  admission.Fragment
	Section                                   string
	AuthoredPath, PayloadPath, IdentityFields []string
}

// Requirement retains bounded realization authority and its private native source owner.
type Requirement struct {
	source                                                       *compiledConcern
	Address, FieldPath, Kind, Domain, GoverningScope, Provenance string
	Posture                                                      *string
	ValueDomain, Constraint, Structure                           admission.Fragment
	ArtifactRequirement                                          *binding.ArtifactRequirementV1
	ObservationScope, ObservationStrength                        string
	RecursivePending, Delegated                                  bool
	ConstraintProvenance, ConstraintBinding                      string
	StructureError                                               bool
	ValueConstraints                                             []ValueConstraint
	ProcessResourceLimits                                        []ProcessResourceLimit
}

// ValueConstraint binds a finite leaf domain to a collection identity and parameter.
type ValueConstraint struct {
	IdentityDigest, Leaf string
	Parameter            []string
	AllowedValues        admission.Fragment
}

// ProcessResourceLimit retains separate soft and hard domains for an exact resource identity.
type ProcessResourceLimit struct {
	IdentityDigest, Resource, Scope string
	Soft, Hard                      admission.Fragment
}

// Authority records the effective posture, source, scope, and verification requirements.
type Authority struct {
	Address, FieldPath, Concern, Posture, Provenance string
	Constraint                                       admission.Fragment
	Domain, Source, GoverningScope                   string
	PayloadPath                                      []string
	ObservationScope, ObservationStrength            string
	Delegated                                        bool
}

// Resolution contains resolved requirements, authority, and ordered diagnostics.
type Resolution struct {
	Requirements []Requirement
	Authority    []Authority
	Diagnostics  []diagnostic.Diagnostic
}

// Decision freezes one delegated concern to an explicit closure.
type Decision struct{ Address, FieldPath, Kind, Closure string }

// ResolveOptions supplies a selected manifest, optional envelope, and frozen decisions.
type ResolveOptions struct {
	Manifest  binding.BackendManifestV2
	Envelope  *binding.RealizationEnvelopeV1
	Decisions []Decision
}
