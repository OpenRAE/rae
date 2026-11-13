package realization

// ownedProjection reads a shape already admitted by the contract or SDL
// owner, or constructed privately in this package. It must follow input
// admission. A broken internal invariant never exposes a source value.
//
//nolint:ireturn // Each private call fixes a concrete projection type.
func ownedProjection[T any](input any) T {
	result, ok := input.(T)
	if !ok {
		panic("realization: invalid owned projection")
	}
	return result
}
