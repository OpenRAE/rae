package arch

import (
	"go/ast"
	"go/parser"
	"go/token"
	"go/types"
	"os"
	"testing"
)

// These compile consumer operations independently of the declaration index.
// They lock the native inputs and composition boundaries from the reviews.
func TestConsumerNativeOperationsCompose(t *testing.T) {
	m := consumerModel(t)
	c := newConsumerTypes(m, os.DirFS(extractionRoot(t)))
	standard, err := c.standardImports()
	if err != nil {
		t.Fatal(err)
	}
	c.existing, err = m.loadConsumerExisting(t.Context(), extractionRoot(t), standard...)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ name, source string }{
		{"inject delivery and readback", `package consumer
import (
 "context"
 c "RUNTIME/runtime/control"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
func use(ctx context.Context,cp c.ControlPlane,actor c.Identity,trigger b.InjectTriggerRequestV1,application b.ParticipantInjectApplicationV1) {
 receipt, _ := cp.SubmitInject(ctx,actor,trigger)
 id, present := receipt.OperationId.Value()
 if !present { return }
 occurrence, _ := cp.InjectOccurrence(ctx,actor,id)
 var _ *b.InjectOccurrenceV1 = occurrence
 outcome, _ := cp.InjectOutcome(ctx,actor,id)
 var _ *b.InjectOccurrenceOutcomeV1 = outcome
 correlation, _ := cp.InjectCorrelation(ctx,actor,id)
 var _ *b.InjectOccurrenceCorrelationV1 = correlation
 manifest, _ := cp.InjectResult(ctx,actor,id)
 var _ *b.AssociatedArtifactManifestV1 = manifest
 bytes, found, _ := cp.InjectArtifact(ctx,actor,id,"artifact")
 if found { _ = len(bytes) }
 delivered, _ := cp.DeliverParticipantInject(ctx,actor,application)
 deliveryID, _ := delivered.OperationId.Value()
 content, _ := cp.InjectDelivery(ctx,actor,deliveryID)
 var _ *b.ParticipantInjectDeliveryV1 = content
 captured, _ := cp.InjectCapture(ctx,actor,id)
 if captured != nil { _ = captured.Status; _ = captured.Observation }
}`},
		{"governed effect inputs", `package consumer
import (
 "context"
 c "RUNTIME/runtime/control"
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
type resolver struct { kind c.EffectKind; intent a.Fragment; address string; trigger *b.InjectTriggerRequestV1; application *b.ParticipantInjectApplicationV1; view *b.ParticipantStatusViewV1; evidence *c.CrossingEvidence }
func (resolver) Resolve(context.Context,map[string]any) (*c.ControlResolution,error) { return nil,nil }
func (resolver) ValidationContext(context.Context,a.Fragment) (a.ControlResolutionContext,error) { return nil,nil }
func (r resolver) EffectOperation(context.Context,a.Fragment,a.ControlResolutionContext) (*c.EffectOperation,error) {
 switch r.kind {
 case c.InjectEffect:
  return &c.EffectOperation{Kind:r.kind,InjectRequest:r.trigger,InjectApplication:r.application,View:r.view,CrossingEvidence:r.evidence,ParticipantAddress:&r.address},nil
 case c.HandoffEffect,c.InterruptEffect:
  return &c.EffectOperation{Kind:r.kind,Intent:r.intent,CrossingEvidence:r.evidence,ParticipantAddress:&r.address},nil
 }
 return nil,nil
}
var _ c.ControlResolver = resolver{}
func use(ctx context.Context,cp c.ControlPlane,actor c.Identity,trigger b.InjectTriggerRequestV1,application b.ParticipantInjectApplicationV1,intent a.Fragment,evidence c.CrossingEvidence) {
 _ = resolver{kind:c.InjectEffect,trigger:&trigger,application:&application,evidence:&evidence}
 _ = resolver{kind:c.HandoffEffect,intent:intent,evidence:&evidence}
 _ = resolver{kind:c.InterruptEffect,intent:intent,evidence:&evidence}
 outcomes, _ := cp.DispatchParticipantControlEffects(ctx,actor,"participant")
 for _,outcome := range outcomes { _ = []string{outcome.EffectID,outcome.Disposition,outcome.ReceiptRef}; _ = outcome.Binding.Document() }
 receipt, _ := cp.RecordParticipantControl(ctx,actor,"participant",intent,&evidence,"key")
 id, _ := receipt.OperationId.Value()
 cancellation, _ := cp.DispatchParticipantCancellation(ctx,actor,id)
 _ = cancellation.ControlDisposition
 _ = cancellation.TargetOperationID
 _ = cancellation.CancellationEffect
 _, _ = cp.ParticipantCancellationStatus(ctx,actor,id)
 _, _ = cp.DeliverParticipantDirectedView(ctx,actor,"participant",b.ParticipantStatusViewV1{},&evidence,"key")
}`},
		{"admitted runtime sequences", `package consumer
import (
 "context"
 "time"
 c "RUNTIME/runtime/control"
 e "RUNTIME/runtime/execution"
 p "RUNTIME/runtime/provider"
 temporal "RUNTIME/runtime/temporal"
 planning "github.com/OpenRAE/rae/implementations/go/processor/planning"
 trial "github.com/OpenRAE/rae/implementations/go/processor/trial"
)
func use(ctx context.Context,cp c.ControlPlane,actor,worker c.Identity,store p.AtomicStore,dispatcher e.Dispatcher,client temporal.Client,planned planning.Result,experiment c.ExperimentRequest,options c.Options) {
 run, _ := cp.OpenRun(ctx,actor,options)
 reference, _ := cp.BindSequence(ctx,actor,c.SequenceOptions{Kind:"run",ScopeID:run.ScopeRef(),ExecutionID:"exec",WorkerID:"worker",StateQueue:"state",Plan:planned.Plan,ActivityBudget:time.Minute,PollInterval:time.Second})
 _, _ = dispatcher.SubmitRuntime(ctx,reference)
 authority, _ := cp.WorkerAuthority(ctx,worker)
 _, _ = temporal.NewRuntimeWorker(client,temporal.RuntimeWorkerOptions{StateQueue:reference.StateQueue,WorkerIdentity:reference.WorkerID,Authority:authority,Capacity:1})
 _, _ = authority.AdvanceRuntime(ctx,reference)
 var _ func(context.Context,c.Identity,e.RuntimeSequenceReference)(string,error) = cp.AdvanceSequence
 realized, _ := trial.RealizeEntry(experiment.Inputs,"entry",trial.RealizationOptions{})
 _ = realized.ExecutionPlan.Manifest()
 experimentID, _ := cp.AdmitExperiment(ctx,actor,experiment)
 experimentReference, _ := cp.BindSequence(ctx,actor,c.SequenceOptions{Kind:"experiment",ScopeID:experimentID,ExecutionID:"experiment-exec",WorkerID:"worker",StateQueue:"state",ActivityBudget:time.Minute,PollInterval:time.Second})
 _, _ = dispatcher.SubmitRuntime(ctx,experimentReference)
 decision, _ := p.NewSequenceDecision(p.SequenceDecision{Reference:reference,ActorID:actor.ActorRef(),AuthorizationScope:[]string{actor.ScopeRef()}})
 _, _ = store.ClaimRuntimeDecision(ctx,decision)
 _, _ = store.LoadRuntimeDecisions(ctx)
 _, _ = p.RuntimeStoreDigest(store.Identity())
 changed := *decision.Sequence(); changed.Reference.WorkerID = "other-worker"
 rebound, _ := p.NewSequenceDecision(changed)
 if decision.ID() == rebound.ID() { _ = p.ValidateIdenticalDecision(decision,rebound) }
}
// The provider invokes this body inside its existing transaction/lock.
func claimWithinTransaction(existing map[string]p.RuntimeDecision,candidate p.RuntimeDecision) (bool,error) {
 if prior := existing[candidate.ID()]; prior != nil {
  if err := p.ValidateIdenticalDecision(prior,candidate); err != nil { return false,err }
  return false,nil
 }
 existing[candidate.ID()] = candidate
 return true,nil
}`},
		{"standard identity", `package consumer
import (
 "time"
 "encoding/json"
 "crypto/tls"
 c "RUNTIME/runtime/control"
 temporal "RUNTIME/runtime/temporal"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
func use() {
 _ = c.Options{Clock:time.Now}
 _ = b.MaterializationArchiveRecordV1{Inventory:b.Field[json.RawMessage]{}}
 _ = temporal.ClientOptions{TLS:&tls.Config{Time:time.Now}}
}`},
		{"invalid standard callback", `package consumer
import c "RUNTIME/runtime/control"
func use() { _ = c.Options{Clock:func()string { return "invalid" }} }
`},
		{"snapshot and owner planning", `package consumer
import (
 "context"
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
 p "github.com/OpenRAE/rae/implementations/go/processor"
 plan "github.com/OpenRAE/rae/implementations/go/processor/planning"
 c "RUNTIME/runtime/control"
)
type defaults struct{}
func (defaults) Resolve(a.Fragment,b.BackendManifestV2) (plan.Closure,error) { return plan.OpenWorld,nil }
func use(ctx context.Context,cp c.ControlPlane,compiled p.Compilation,current b.RuntimeSnapshotV1,manifest b.BackendManifestV2,profiles b.DomainProfileResolutionContextV1,processor b.ProcessorManifestV2) {
 mixed, _ := cp.MixedControlPlanningAdmission(ctx)
 target,run,instance := "target","run","instance"
 result, _ := plan.PlanWithManifest(compiled,manifest,plan.Options{Snapshot:&current,Scope:&plan.Scope{TargetName:&target,RunID:&run,InstantiationID:&instance},ApparatusDefault:defaults{},ArtifactAvailability:[]plan.ArtifactAvailability{{Address:"provision.node.a",AvailableArtifactDigests:[]string{"digest"}}},ProfileContext:&profiles,MixedControlAdmission:mixed,RefreshEvaluation:true,ProcessorManifest:&processor})
 _ = result.Plan.Context().Snapshot
 _ = result.Plan.Context().ApparatusDecisions
}`},
		{"live policy owners", `package consumer
import (
 "context"
 c "RUNTIME/runtime/control"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
type owner struct{}
func (owner) Resolve(context.Context,c.CrossingIntent,b.RuntimeSnapshotV1) (c.CrossingResolution,error) { return c.CrossingResolution{Gates:c.CrossingGates{Visibility:"permit"},AllowedDowngrades:map[string]string{}},nil }
func (owner) ValidationContext(context.Context,b.RuntimeSnapshotV1,string) (c.CrossingValidation,error) { return c.CrossingValidation{},nil }
func (owner) ResolveParticipantViewEvidence(context.Context,c.ViewEvidenceRequest) (c.CrossingEvidence,error) { return c.CrossingEvidence{},nil }
func (owner) ResolveFlowSinkDecision(_ context.Context,r c.FlowSinkRequest) (c.FlowSinkResolution,error) {
 _ = r.ExpectedHistoryHeadRefs
 _ = r.Crossing.ExpectedHistoryHeads
 _ = r.Intent.Subject
 return c.FlowSinkResolution{},nil
}
func use(ctx context.Context,snapshot b.RuntimeSnapshotV1) {
 enforce := true
 options := c.Options{CrossingPolicy:owner{},FlowSink:owner{},EnforceFinalSinkFlowControl:&enforce}
 _, _ = options.CrossingPolicy.Resolve(ctx,c.CrossingIntent{},snapshot)
 _, _ = options.CrossingPolicy.ValidationContext(ctx,snapshot,"participant")
 _, _ = options.CrossingPolicy.ResolveParticipantViewEvidence(ctx,c.ViewEvidenceRequest{Snapshot:snapshot})
 _, _ = options.FlowSink.ResolveFlowSinkDecision(ctx,c.FlowSinkRequest{Snapshot:snapshot,ExpectedHistoryHeadRefs:[]string{"head"}})
}
`},
		{"core inject and supervision", `package consumer
import (
 "context"
 c "RUNTIME/runtime/control"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
func use(ctx context.Context,cp c.ControlPlane,identity c.Identity,trigger b.InjectTriggerRequestV1) {
 _, _ = cp.SubmitInject(ctx,identity,trigger)
 control, _ := cp.SuperviseOperation(ctx,identity,c.SupervisionRequest{OperationID:"op",ControlID:"control",Action:c.Cancel})
 _, _ = cp.SubmitOperationControl(ctx,identity,control)
 response, _ := cp.ControlResponse(ctx,identity,"op","control")
 var _ *b.BackendOperationResponseV1 = response
 _ = cp.StopAdmission(ctx,identity)
 _, _ = cp.ResolveIndeterminateOperation(ctx,identity,c.ResolutionRequest{OperationID:"op",IdempotencyKey:"resolve",Disposition:c.AcceptCurrentSnapshot})
}`},
		{"artifact load then admit", `package consumer
import (
 "io"
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
 v "github.com/OpenRAE/rae/implementations/go/contract/validation"
 i "github.com/OpenRAE/rae/implementations/go/base/ingress"
)
func use(validator *a.Validator,parent a.AssociatedArtifactsContext,source []byte,payload io.Reader) {
 manifest, _ := a.LoadAssociatedManifest(validator,source,i.Limits{})
 var _ b.AssociatedArtifactManifestV1 = manifest
 _, _ = a.AssociatedArtifactSetDigest(manifest)
 admitted, _ := a.ValidateAssociatedManifest(validator,manifest,parent,map[string]io.Reader{"artifact":payload},a.DefaultAssociatedArtifactLimits())
 var _ v.Value = admitted
}`},
		{"scalar and collection realization", `package consumer
import (
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
 i "github.com/OpenRAE/rae/implementations/go/base/ingress"
 r "github.com/OpenRAE/rae/implementations/go/processor/realization"
)
func use(constraint a.Fragment) {
 scalar, _ := a.AdmitFragment(a.RealizationValue,"linux",i.Limits{})
 projectedScalar, _ := r.ProjectConcern("operating-system",scalar,false,false)
 _ = projectedScalar.Document().(string)
 collection, _ := a.AdmitFragment(a.RealizationValue,[]any{map[string]any{"name":"package"}},i.Limits{})
 projected, _ := r.ProjectConcern("runtime-packages",collection,false,false)
 _ = projected.Document().([]any)
 _, _ = a.EvaluateRealizationConstraint(constraint,projected,a.DefaultConstraintLimits())
}`},
		{"native values", `package consumer
import (
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
 c "github.com/OpenRAE/rae/implementations/go/contract/concept"
 r "github.com/OpenRAE/rae/implementations/go/contract/runtime"
 t "github.com/OpenRAE/rae/implementations/go/processor/trial"
 i "github.com/OpenRAE/rae/implementations/go/base/ingress"
)
func use() {
 _, _ = a.AdmitFragment(a.TrialInputRefs, map[string]any{}, i.Limits{})
 _ = c.Subject{SubjectKind:"node", OwningContractID:"sdl-authoring-input-v1", LifecyclePhase:"expanded-authoring", CanonicalRef:"nodes.a", ArtifactDigest:"sha256:x"}
 _ = c.SchemeSnapshot{SchemeID:"s", Authority:"a", Revision:"1", SourceLocator:"https://example.org", SourceDigest:"sha256:x", Concepts:[]c.SnapshotTerm{{ConceptID:"x", Status:"current"}}}
 _ = r.RealizationPreparation{Operations:[]r.ProvisionOperation{{Address:"nodes.a", Payload:map[string]any{}}}}
 _ = t.Request{Limits:t.DefaultLimits(), MixedCompositionLimits:t.DefaultMixedCompositionLimits()}
 _ = t.Request{RealizationAssignments:map[string]a.Fragment{}}
}`},
		{"configuration normalization", `package consumer
import (
 "context"
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
)
type owner struct{}
func (owner) ValidateAndNormalize(_ context.Context, c a.ParticipantConfiguration) (a.ParticipantConfiguration,error) { return c,nil }
func (owner) ValidateControlContextReference(context.Context,string,a.ControlContextSelection) error { return nil }
func use(ctx context.Context) {
 _, _ = a.RealizeParticipantConfiguration(ctx,a.ParticipantConfigurationRequest{Validator:owner{}, ControlContext:owner{}, Overrides:[]a.ConfigurationOverride{{TargetID:"x",Value:a.BindingValue{Kind:"literal",Literal:"v"}}}})
}`},
		{"planner authorization", `package consumer
import (
 "context"
 c "RUNTIME/runtime/control"
 p "github.com/OpenRAE/rae/implementations/go/processor/planning"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
func use(ctx context.Context, plane c.ControlPlane, identity c.Identity, planned p.Result, snapshot b.RuntimeSnapshotV1) {
 registered, _ := plane.RegisterPlannerProducedPlan(ctx,planned.Plan)
 command, _ := c.PlanCommand(registered,c.Provisioning,false)
 _, _ = plane.Submit(ctx,identity,c.Request{Command:command,BaseSnapshot:&snapshot,IdempotencyKey:"key"})
 control, _ := c.NewParticipantControlBinding(c.ControlInstallation{})
 _ = c.Options{ParticipantControl:control}
 _, _ = c.NewMixedControlBinding(planned.Plan.Model(),nil,nil)
 _, _ = c.NewInjectDeliveryBinding(planned.Plan.Model(),nil)
}`},
		{"scoped Temporal workers", `package consumer
import (
 c "RUNTIME/runtime/control"
 e "RUNTIME/runtime/execution"
 t "RUNTIME/runtime/temporal"
 b "github.com/OpenRAE/rae/implementations/go/backend"
)
func use(client t.Client, authority e.WorkerAuthority, backend b.OperationProvider) {
 config := t.Configuration{Namespace:"n",WorkflowQueue:"w",EffectQueue:"e",ControlQueue:"c",WorkerIdentity:"worker"}
 adapter, _ := t.New(client,config)
 _ = c.Options{Distributed:adapter}
 _, _ = t.NewWorker(client,config,t.WorkerOptions{Provider:backend,EffectAuthority:authority,ControlAuthority:authority})
 var _ e.Dispatcher = adapter
}`},
		{"opaque record claims", `package consumer
import (
 "context"
 p "RUNTIME/runtime/provider"
)
func use(ctx context.Context,s p.AtomicStore,existing,candidate p.OperationRecord) {
 identity := candidate.ClaimIdentity()
 _, _ = p.IdempotencyClaimIdentity(candidate.AdmissionContext(),identity.IdempotencyKey)
 _ = candidate.RequestFingerprint()
 _ = candidate.DecisionHistoryHeads()
 _ = candidate.ResultHistoryHeads()
 _ = p.ValidateIdempotencyReplay(existing,candidate,"")
 admission := candidate.AdmissionContext()
 _, _ = s.FindByIdempotency(ctx,identity.IdempotencyKey,&admission)
 _ = p.ValidateNewClaim(candidate,p.ClaimState{Records:[]p.OperationRecord{existing}},p.ClaimOptions{})
}`},
		{"atomic supervision", `package consumer
import (
 "context"
 "errors"
 p "RUNTIME/runtime/provider"
)
func use(ctx context.Context,s p.AtomicStore,old,next p.OperationRecord,audit p.AuditEvent) {
 _ = p.ValidateInvocationTransition(old,next,audit)
 _, _ = s.CommitInvocationTransition(ctx,old,next,audit)
 _, _ = s.AdmitExecutionGeneration(ctx)
 _, _ = s.EffectAdmissionStopped(ctx)
 _ = s.StopEffectAdmission(ctx,audit)
 _ = p.RecordsEqual(old,next)
 _ = errors.Is(p.ErrConflict,p.ErrConflict)
}`},
		{"native backend protocols", `package consumer
import (
 "context"
 b "github.com/OpenRAE/rae/implementations/go/backend"
 c "github.com/OpenRAE/rae/implementations/go/contract/binding"
 r "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)
func use(ctx context.Context,backend b.ControlledAutonomousParticipantRuntime,provider b.OperationProvider,native r.NativeActionExecution,profiles b.ProfilePreparingProvisioner,snapshot c.RuntimeSnapshotV1) {
 request, _ := backend.BindAutonomousAction(ctx,b.AutonomousActionBinding{ParticipantAddress:"p"},snapshot)
 result, _ := backend.AdmitAutonomousAction(ctx,request,snapshot)
 _ = result.ActionResult
 outcome, _ := native.Invoke(ctx,request,snapshot)
 _ = outcome.ApplyResult
 _ = outcome.ActionResult
 _ = outcome.PostStateDigest
 _, _ = backend.AdmitActionsConcurrently(ctx,[]r.ParticipantActionRequest{request},snapshot,2)
 _, _ = backend.ControlExecution(ctx,c.ParticipantExecutionControlV1{},snapshot)
 _, _ = backend.ExecutionState(ctx,"scope",snapshot)
 _, _ = provider.OperationCapabilities(ctx)
 _, _ = provider.CheckOperation(ctx,c.BackendOperationRequestV1{})
 _ = profiles.DomainProfileContext()
 _, _ = profiles.ValidateProfiles(ctx,c.ProvisioningPlanV1{})
}`},
		{"single plan schedule", `package consumer
import (
 t "github.com/OpenRAE/rae/implementations/go/processor/trial"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
)
func use(plan b.AdmittedTrialPlanV1) {
 schedule, _ := t.PlanBatchSchedule(plan)
 _ = []string{schedule.PlanID,schedule.PlanDigest,schedule.SchedulingPolicyID}
 _ = schedule.IsolationProofRef
 _ = schedule.AdmittedParallelismCeiling
 for _,entry := range schedule.Entries { _ = []string{entry.PlanEntryID,entry.RunID}; _ = entry.DispatchOrdinal }
}`},
		{"manifest coordinates", `package consumer
import t "github.com/OpenRAE/rae/implementations/go/processor/trial"
var participant = t.ParticipantManifestKey{ParticipantAddress:"p",ImplementationName:"i",ImplementationVersion:"1",ManifestVersion:"v1"}
var apparatus = t.ApparatusManifestKey{ComponentKind:"processor",ComponentName:"i",ComponentVersion:"1",ManifestVersion:"v2"}
var validator = t.ConfigurationValidatorKey{ImplementationName:"i",ImplementationVersion:"1"}
`},
		{"independent experiment admission", `package consumer
import (
 a "github.com/OpenRAE/rae/implementations/go/contract/admission"
 b "github.com/OpenRAE/rae/implementations/go/contract/binding"
 s "github.com/OpenRAE/rae/implementations/go/sdl"
)
type resolver struct{}
func (resolver) Resolve(string,string,string) (a.ScenarioBindingResolution,error) { return a.ScenarioBindingResolution{CanonicalTargetID:"canonical",AllowedValueKinds:[]string{"literal"},Owner:a.BindingOwner{ContractID:"owner"}},nil }
func use(family s.Scenario) {
 _, _ = s.ValidateExperimentSelectionAgainstFamily(b.ExperimentAuthoringInputV1{},family)
 _, _ = a.ValidateExperimentBindingTargets(b.ExperimentBindingDescriptorsV1{},resolver{},map[a.ParticipantManifestKey]b.ParticipantImplementationManifestV1{},map[a.ApparatusManifestKey]a.ApparatusManifest{})
}`},
		{"lock trust facts", `package consumer
import (
 "context"
 m "github.com/OpenRAE/rae/implementations/go/sdl/module"
 s "github.com/OpenRAE/rae/implementations/go/sdl"
)
func use(ctx context.Context) {
 record := m.LockRecord{Source:"local:lib",Namespace:"lib",RequestedVersion:"*",ResolvedSource:"local:lib",ModuleID:"lib",ModuleVersion:"1",ManifestDigest:"m",ContentDigest:"c",ExportHash:"e",SignerID:"signer"}
 facts := m.VerificationFacts{Record:record,Registry:"registry",SignerPublicKey:"key",SignatureVerified:true,ManifestVerified:true,ContentVerified:true,ExportsVerified:true}
 policy := m.DefaultPolicy()
 _ = policy.AdmitModule(ctx,facts)
 _, _ = s.ParseContext(s.SourceContext{Lock:&m.Lockfile{Imports:[]m.LockRecord{record}},Trust:policy},s.DefaultParseOptions())
}`},
		{"imported language sources", `package consumer
import (
 "io/fs"
 s "github.com/OpenRAE/rae/implementations/go/sdl"
 l "github.com/OpenRAE/rae/implementations/go/sdl/language"
)
func use(files fs.FS) {
 source := s.SourceContext{Root:"root.sdl",RootBytes:[]byte("name: x"),FS:files}
 _, _ = l.Diagnostics(source,s.DefaultParseOptions())
 _, _ = l.Completions(source,s.DefaultParseOptions(),"/nodes","")
 _, _ = l.ApplyEdit(source,s.DefaultParseOptions(),l.Edit{Pointer:"/name",Value:"y"})
 _, _ = l.Format(source,s.DefaultParseOptions())
}`},
		{"parser controls", `package consumer
import s "github.com/OpenRAE/rae/implementations/go/sdl"
func use() {
 limits := s.Limits{MaxInputBytes:1,MaxScalarBytes:1,MaxComposedBytes:1,MaxDepth:1,MaxNodes:1,MaxAliases:1,MaxExpandedNodes:1,MaxImports:1,MaxComposedNodes:1,MaxCompositionDepth:1,MaxNamespaceDepth:1}
 _ = limits.Validate()
 options := s.ParseOptions{Limits:limits,SourceFormat:s.SourceFormat,MigrationPolicy:s.AcceptMigration,RequiredSemanticRevision:"raes-progressive-semantics/v1"}
 _ = options.Validate()
 _, _ = s.Parse([]byte("name: x"),options)
}`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			fset := token.NewFileSet()
			file, parseErr := parser.ParseFile(fset, "consumer.go", tc.source, 0)
			if parseErr != nil {
				t.Fatal(parseErr)
			}
			config := types.Config{Importer: c}
			_, checkErr := config.Check("example.com/consumer", fset, []*ast.File{file}, nil)
			if (checkErr != nil) != (tc.name == "invalid standard callback") {
				t.Fatalf("consumer type check = %v", checkErr)
			}
		})
	}
}
