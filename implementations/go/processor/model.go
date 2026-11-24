package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// RuntimeModel is an immutable compiled scenario issued by this package.
type RuntimeModel interface {
	Document() map[string]any
	View() CompiledScenario
	compiledModel()
}

// Compilation retains the native model, resource counts, and ordered diagnostics.
type Compilation interface {
	Model() RuntimeModel
	Document() map[string]any
	Nodes() int
	Networks() int
	Diagnostics() []diagnostic.Diagnostic
	compiledScenario()
}

// ComponentOptions records which backend components the scenario needs.
type ComponentOptions struct{ WithOrchestrator, WithEvaluator, WithParticipantRuntime, WithTime, WithObservation bool }

// ResourcePayload is an immutable projection for a published operation payload.
// Compiler passes do not decode it or use it as their shared model.
type ResourcePayload struct{ data []byte }

// NodeCapabilities retains typed node facts for capability comparisons.
type NodeCapabilities struct {
	Kind, OSFamily, OSDistribution, OSVersion, Architecture string
	Count                                                   *json.Number
	NetworkNamespaceTarget                                  string
}

// Resource retains compiled operation facts and separate ordering and refresh dependencies.
type Resource struct {
	SelectedProfiles                          []binding.DomainProfileBindingV1
	Address, Name, Domain, Kind               string
	OrderingDependencies, RefreshDependencies []string
	Payload                                   ResourcePayload
	Node                                      *NodeCapabilities
	RequiredFeatures                          []string
	RegenerationScope                         string
	Evaluation                                *EvaluationFacts
	HasACLs, UsesAssertionRefs                bool
	TargetAddress, ContentType                string
	AccountFeatures                           []string
	Topology                                  *DomainTopology
	Artifact                                  *ArtifactFacts
	ServiceMaterialization                    *ServiceMaterialization
	WorkflowStatePredicateFeatures            []string
}

// DomainTopology binds a domain role to its authority account and controllers.
type DomainTopology struct {
	DomainID, Profile, DNSName, NetBIOSName, AuthorityAccountAddress, Role string
	ControllerAddresses                                                    []string
	ProfileBinding                                                         *binding.DomainProfileBindingV1
}

// ArtifactConsumer binds a generated output to its declared delivery target.
type ArtifactConsumer struct {
	Node, Content, TargetAddress, DeliveryMode, Output, EnvironmentVariable, EnvironmentFile string
	Classification                                                                           string
}

// ArtifactFacts retains generator, regeneration, output, and delivery requirements.
type ArtifactFacts struct {
	Kind, RegenerationScope    string
	DeliveryModes, OutputNames []string
	Consumers                  []ArtifactConsumer
	GeneratorBinding           *binding.DomainProfileBindingV1
}

// ServiceMaterialization binds content to an exact service interface and readback policy.
type ServiceMaterialization struct {
	TargetServiceAddress, InterfaceProfile, ProfileVersion                            string
	ContentType, Operation, ConflictPolicy, Readback                                  string
	CanonicalContentDigest, SharedServiceRelationshipRef, ConsumerTenantRef           string
	MutableStateOwner, ResetGenerationOwner, CanonicalFieldSchemaDigest               string
	ReadbackAssertionAddresses, EvidenceRequirementRefs, ObservationBoundaryAddresses []string
	FieldSemantics                                                                    map[string]string
	ProfileBinding                                                                    *binding.DomainProfileBindingV1
}

// EvaluationFacts retains predicate and evidence requirements for planning.
type EvaluationFacts struct {
	PredicateKind, Quantifier, EvaluationBasis, Role, RequiredTimeDomain string
	DeferredExpected                                                     bool
	EvidenceChannels, UnresolvedEvidenceChannelRefs                      []string
}

// CapabilityConstraint retains a finite parameter domain for one resource concern.
type CapabilityConstraint struct {
	Address, Concern string
	Parameter        []string
	AllowedValues    []Scalar
}

// Scalar is an immutable typed scalar admitted by the compiler.
type Scalar struct {
	kind  string
	value any
}

// TimeDomain retains an exact rational tick period and its declared epoch.
type TimeDomain struct {
	Address, Kind, Epoch, Visibility, Description string
	TickNumerator, TickDenominator                json.Number
}

// Clock retains authority and movement capabilities for a compiled time domain.
type Clock struct {
	Address, TimeDomainAddress, AuthorityKind, AuthorityRef, Monotonicity, Description string
	SupportsPause, SupportsReset, SupportsJump                                         bool
}

// TimeMapping retains an exact scale and offset between time domains.
type TimeMapping struct {
	Address, SourceDomainAddress, TargetDomainAddress, Kind, Description string
	ScaleNumerator, ScaleDenominator, OffsetTicks                        json.Number
}

// TimePolicy retains progression, synchronization, reset, and replay requirements.
type TimePolicy struct {
	Address, ClockAddress, AdvancementMode, SynchronizationMode, ResetBehavior, ReplayBehavior, Description string
	PacingNumerator, PacingDenominator                                                                      json.Number
	StepTicks, DriftBoundTicks                                                                              *json.Number
}

// TemporalConstraint binds exact time bounds to compiled subjects and a clock.
type TemporalConstraint struct {
	Address, Kind, ClockAddress, Description                                      string
	SubjectAddresses                                                              []string
	StartTick, StartMicrostep, EndTick, EndMicrostep, DurationTicks, CadenceTicks *json.Number
}

// CompiledTimeModel contains the typed time facts used by all compiler stages.
type CompiledTimeModel struct {
	Domains             []TimeDomain
	Clocks              []Clock
	Mappings            []TimeMapping
	ProgressionPolicies []TimePolicy
	Constraints         []TemporalConstraint
}

// Definition retains a compiled reusable declaration at its canonical address.
type Definition struct {
	Address, Name, Kind string
	Payload             ResourcePayload
}

// CompiledScenario is a copied view of compiled facts; changing it cannot alter its owner.
type CompiledScenario struct {
	Descriptive, AugmentationScopeRequired bool
	Name                                   string
	Original                               sdl.Scenario
	Resources                              []Resource
	Definitions                            []Definition
	ParticipantResources                   []Resource
	TimeModel                              CompiledTimeModel
	HasTimeModel                           bool
	CapabilityConstraints                  []CapabilityConstraint
	RealizationRequirements                []realization.Requirement
	RealizationAuthority                   []realization.Authority
	DescriptorProfiles                     []binding.DomainProfileBindingV1
	ProfileAuthority                       *binding.PlanRealizationProfilesV1
	ObservationDemands                     []ObservationDemand
	CaptureDemands                         []CaptureDemand
	ExecutionPolicies                      []ExecutionPolicy
	Diagnostics                            []diagnostic.Diagnostic
}

// ObservationDemand binds a sealed effective demand to its owning requirement.
type ObservationDemand struct {
	Demand                             admission.Fragment
	Address, RequirementID, ContractID string
	Payload                            ResourcePayload
}

// CaptureDemand retains the independent dimensions of a declared capture requirement.
type CaptureDemand struct {
	DemandID, CaptureRequirementRef, CaptureKind, Sensitivity, Disclosure, ExportPolicy     string
	FieldSelectors, ArtifactRoles, MediaTypes, SourceClasses, SourceRefs, Scopes, ScopeRefs []string
	ChannelKinds, ChannelRefs, WindowKinds, IntegrityModes, RetentionPolicyRefs             []string
	RedactionPolicy                                                                         *string
	Address, CaptureSpecRef, BoundaryRef, OutputContract, MediaType                         string
	Payload                                                                                 ResourcePayload
}

// ExecutionPolicy binds an admitted effective policy to one compiled operation.
type ExecutionPolicy struct {
	Address, Domain string
	Policy          admission.Fragment
}

// CompileOptions supplies parameter values, profile authority, and capture artifacts.
type CompileOptions struct {
	Parameters       map[string]any
	ProfileAuthority *binding.PlanRealizationProfilesV1
	Capture          CaptureInputs
}
