package authoring

func modelNumberEqual(left, right any) bool {
	a, ok := modelInteger(left)
	b, present := modelInteger(right)
	return ok && present && a.Cmp(b) == 0
}
func modelLess(left, right any) bool {
	a, ok := modelInteger(left)
	b, present := modelInteger(right)
	return ok && present && a.Cmp(b) < 0
}
