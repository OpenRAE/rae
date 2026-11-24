package authoring

// AdmitModuleSource checks source syntax and its full native construction
// independently of import expansion, semantic execution, or caller claims.
func (p *Parser) AdmitModuleSource(raw []byte) error {
	_, err := p.decodeDocument(raw, "", "reject", true)
	return err
}
