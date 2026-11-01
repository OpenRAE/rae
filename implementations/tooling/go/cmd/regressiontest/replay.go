package main

import (
	"bytes"
	"context"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"golang.org/x/tools/go/ast/astutil"
)

// declKey names a top-level declaration of a test package: the package name,
// and the name of the declaration or of the receiver type of a method.
type declKey struct {
	pkg, name string
}

// restoreReplay prepares the base package in dir for a replay of the named
// regression tests. It removes the base test files and testdata, writes the
// head test files pruned to the declarations that the tests need, and restores
// the head testdata. Thus base and head test code never mix, and another new
// test cannot change the outcome.
func restoreReplay(ctx context.Context, worktree, head, dir string, names []string) error {
	if err := removeBaseTests(filepath.Join(worktree, dir)); err != nil {
		return err
	}
	fset := token.NewFileSet()
	files, err := headTestFiles(ctx, fset, worktree, head, dir)
	if err != nil {
		return err
	}
	pruned, err := pruneTests(fset, files, names)
	if err != nil {
		return err
	}
	for file, source := range pruned {
		if err = os.WriteFile(filepath.Join(worktree, file), source, 0o600); err != nil {
			return err
		}
	}
	testdata := path.Join(filepath.ToSlash(dir), "testdata")
	listed, err := git(ctx, worktree, "ls-tree", "--name-only", head, "--", testdata)
	if err != nil || listed == "" {
		return err
	}
	_, err = git(ctx, worktree, "restore", "--source="+head, "--worktree", "--", testdata)
	return err
}

// removeBaseTests removes the test files and the testdata of the base package
// in dir.
func removeBaseTests(dir string) error {
	files, err := filepath.Glob(filepath.Join(dir, "*_test.go"))
	if err != nil {
		return err
	}
	for _, file := range append(files, filepath.Join(dir, "testdata")) {
		if err = os.RemoveAll(file); err != nil {
			return err
		}
	}
	return nil
}

// headTestFiles parses the test files of the package in dir at the head commit.
func headTestFiles(ctx context.Context, fset *token.FileSet, worktree, head, dir string) (map[string]*ast.File, error) {
	listed, err := git(ctx, worktree, "ls-tree", "--name-only", head, "--", filepath.ToSlash(dir)+"/")
	if err != nil {
		return nil, err
	}
	files := map[string]*ast.File{}
	for name := range strings.SplitSeq(listed, "\n") {
		if !strings.HasSuffix(name, "_test.go") {
			continue
		}
		source, err := git(ctx, worktree, "show", head+":"+name)
		if err != nil {
			return nil, err
		}
		// astutil.UsesImport needs the object resolution of the parser.
		file, err := parser.ParseFile(fset, name, source, parser.ParseComments)
		if err != nil {
			return nil, err
		}
		files[name] = file
	}
	return files, nil
}

// pruneTests keeps, in the test files of one package directory, the
// declarations that the named tests need. The result maps each file that keeps
// a declaration to its formatted source.
func pruneTests(fset *token.FileSet, files map[string]*ast.File, names []string) (map[string][]byte, error) {
	kept := neededDecls(files, names)
	pruned := map[string][]byte{}
	for name, file := range files {
		file.Decls = slices.DeleteFunc(file.Decls, func(decl ast.Decl) bool { return !keepDecl(decl, kept) })
		if !slices.ContainsFunc(file.Decls, isCode) {
			continue
		}
		removeUnusedImports(fset, file)
		file.Comments = ast.NewCommentMap(fset, file, file.Comments).Filter(file).Comments()
		var source bytes.Buffer
		if err := format.Node(&source, fset, file); err != nil {
			return nil, err
		}
		pruned[name] = source.Bytes()
	}
	return pruned, nil
}

// neededDecls returns the declarations that the named tests need, with TestMain
// and each init function. An identifier needs each declaration of its name in
// its test package, and in the internal test package for an external one.
func neededDecls(files map[string]*ast.File, names []string) map[ast.Node]bool {
	index := map[declKey][]ast.Node{}
	var queue []declKey
	for _, file := range files {
		pkg := file.Name.Name
		indexFile(index, pkg, file)
		queue = append(queue, declKey{pkg, "TestMain"}, declKey{pkg, "init"})
		for _, name := range names {
			queue = append(queue, declKey{pkg, name})
		}
	}
	kept := map[ast.Node]bool{}
	for len(queue) > 0 {
		key := queue[0]
		queue = queue[1:]
		for _, node := range index[key] {
			if !kept[node] {
				kept[node] = true
				queue = append(queue, references(key.pkg, node)...)
			}
		}
	}
	return kept
}

// references returns the keys that the identifiers in node can name.
func references(pkg string, node ast.Node) []declKey {
	var keys []declKey
	ast.Inspect(node, func(n ast.Node) bool {
		if ident, ok := n.(*ast.Ident); ok {
			keys = append(keys, declKey{pkg, ident.Name}, declKey{strings.TrimSuffix(pkg, "_test"), ident.Name})
		}
		return true
	})
	return keys
}

// indexFile records each top-level declaration of file under its key.
func indexFile(index map[declKey][]ast.Node, pkg string, file *ast.File) {
	for _, decl := range file.Decls {
		if fn, ok := decl.(*ast.FuncDecl); ok {
			index[funcKey(pkg, fn)] = append(index[funcKey(pkg, fn)], fn)
		}
		if gen, ok := decl.(*ast.GenDecl); ok {
			for _, spec := range gen.Specs {
				for _, name := range specNames(spec) {
					index[declKey{pkg, name}] = append(index[declKey{pkg, name}], spec)
				}
			}
		}
	}
}

// funcKey returns the key of a function. A method has the key of its receiver
// type, so that a kept type keeps its methods.
func funcKey(pkg string, fn *ast.FuncDecl) declKey {
	if fn.Recv == nil {
		return declKey{pkg, fn.Name.Name}
	}
	return declKey{pkg, receiverType(fn.Recv.List[0].Type)}
}

// specNames returns the names that a type or value spec declares.
func specNames(spec ast.Spec) []string {
	var names []string
	if typeSpec, ok := spec.(*ast.TypeSpec); ok {
		names = append(names, typeSpec.Name.Name)
	}
	if valueSpec, ok := spec.(*ast.ValueSpec); ok {
		for _, ident := range valueSpec.Names {
			names = append(names, ident.Name)
		}
	}
	return names
}

// receiverType returns the name of the type of a method receiver.
func receiverType(expr ast.Expr) string {
	for {
		switch e := expr.(type) {
		case *ast.StarExpr:
			expr = e.X
		case *ast.IndexExpr:
			expr = e.X
		case *ast.IndexListExpr:
			expr = e.X
		case *ast.Ident:
			return e.Name
		default:
			return ""
		}
	}
}

// keepDecl reports whether decl stays in a pruned file, and drops the specs
// that no kept declaration needs. Imports stay until removeUnusedImports.
func keepDecl(decl ast.Decl, kept map[ast.Node]bool) bool {
	gen, ok := decl.(*ast.GenDecl)
	if !ok {
		return kept[decl]
	}
	if gen.Tok == token.IMPORT {
		return true
	}
	gen.Specs = slices.DeleteFunc(gen.Specs, func(spec ast.Spec) bool { return !kept[spec] })
	return len(gen.Specs) > 0
}

// isCode reports whether decl is a declaration other than an import.
func isCode(decl ast.Decl) bool {
	gen, ok := decl.(*ast.GenDecl)
	return !ok || gen.Tok != token.IMPORT
}

// removeUnusedImports deletes each import that the pruned file no longer uses.
// Blank and dot imports stay.
func removeUnusedImports(fset *token.FileSet, file *ast.File) {
	for _, spec := range slices.Clone(file.Imports) {
		// The parser accepts only an import path that unquotes.
		importPath, _ := strconv.Unquote(spec.Path.Value)
		name := ""
		if spec.Name != nil {
			name = spec.Name.Name
		}
		if name != "_" && name != "." && !astutil.UsesImport(file, importPath) {
			astutil.DeleteNamedImport(fset, file, name, importPath)
		}
	}
}
