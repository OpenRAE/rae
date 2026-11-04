package admission

// InjectRetryContext identifies the existing claim and independently authorized
// actor whose exact retry is checked.
type InjectRetryContext interface {
	InjectOccurrence() []byte
	ActorID() string
}

// InjectClaimsProvider supplies the bounded claim set of one target/run store.
type InjectClaimsProvider interface{ InjectClaims() [][]byte }

// InjectClaimsContext retains the original name for InjectClaimsProvider.
type InjectClaimsContext = InjectClaimsProvider

// InjectOutcomeContext supplies the claimed occurrence and exact invocation.
type InjectOutcomeContext interface {
	InjectOccurrence() []byte
	OperationRequest() []byte
}

// InjectCorrelationContext supplies all source artifacts for recomputing the
// participant correlation from a successful applied effect.
type InjectCorrelationContext interface {
	InjectOutcomeContext
	InjectOutcome() []byte
}
