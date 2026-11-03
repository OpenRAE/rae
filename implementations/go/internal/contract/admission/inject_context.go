package admission

// InjectRetryContext identifies the existing claim and independently authorized
// actor whose exact retry is checked.
type InjectRetryContext interface {
	InjectOccurrence() []byte
	ActorID() string
}

// InjectClaimsContext supplies the bounded claim set of one target/run store.
type InjectClaimsContext interface{ InjectClaims() [][]byte }

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
