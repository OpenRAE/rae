'use strict';

const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {mkdtempSync, readFileSync, rmSync, writeFileSync} = require('node:fs');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const {test} = require('node:test');
const {Manifest} = require('release-please');
const {useReleaseRange, maintainReleasePr} = require('./run.cjs');

const config = JSON.parse(readFileSync(join(__dirname, '../../..', 'release-please-config.json')));

function fixture(t, message = 'refactor!: move public modules (#1811)') {
  const cwd = mkdtempSync(join(tmpdir(), 'raes-release-range-'));
  t.after(() => rmSync(cwd, {recursive: true, force: true}));
  const git = (...args) => execFileSync('git', args, {cwd, encoding: 'utf8'}).trim();
  git('init', '-q', '-b', 'main');
  git('config', 'core.hooksPath', '/dev/null');
  git('config', 'commit.gpgsign', 'false');
  git('config', 'tag.gpgsign', 'false');
  git('config', 'user.email', 'test@example.invalid');
  git('config', 'user.name', 'Release Test');
  function commit(message, date) {
    execFileSync('git', ['commit', '-q', '--allow-empty', '-m', message], {
      cwd, env: {...process.env, GIT_AUTHOR_DATE: date, GIT_COMMITTER_DATE: date},
    });
    return git('rev-parse', 'HEAD');
  }
  const initial = commit('fix: previous release content', '2026-10-30T00:00:00Z');
  git('checkout', '-q', '-b', 'dev');
  const breaking = commit(message, '2026-11-01T00:18:06Z');
  git('checkout', '-q', 'main');
  const base = commit('chore(main): release 10.3.0', '2026-11-01T00:18:34Z');
  git('tag', 'v10.3.0');
  git('merge', '-q', '--no-ff', 'dev', '-m', 'Merge pull request #1824 from example/dev');
  const head = git('rev-parse', 'HEAD');
  git('remote', 'add', 'origin', cwd);
  writeFileSync(join(cwd, '.release-please-manifest.json'), JSON.stringify({'.': '10.3.0'}));
  const object = sha => ({sha, message: git('show', '-s', '--format=%B', sha), files: ['source.py']});
  const commits = [head, base, breaking, initial].map(object);
  const github = {
    repository: {owner: 'example', repo: 'raes', defaultBranch: 'main'},
    async *mergeCommitIterator() { yield* commits; },
    async *releaseIterator() { yield {tagName: 'v10.3.0', sha: base, notes: ''}; },
    async *tagIterator() { yield {name: 'v10.3.0', sha: base}; },
    async getFileJson(path) { return path === 'release-please-config.json' ? config : {'.': '10.3.0'}; },
    async getFileContentsOnBranch(path) {
      const contents = path === 'release-please-config.json' ? config : {'.': '10.3.0'};
      return {parsedContent: JSON.stringify(contents)};
    },
    async findFilesByFilenameAndRef() { return []; },
  };
  return {cwd, head, base, breaking, initial, commits, github, git, commit};
}

async function candidates(github) {
  const manifest = await Manifest.fromManifest(github, 'main');
  return manifest.buildPullRequests();
}

test('older-dated breaking refactor produces a major release and breaking notes', async t => {
  const f = fixture(t);
  assert.deepEqual(await candidates(f.github), [], 'upstream chronological scan reproduces #1841');
  useReleaseRange(f.github, f.cwd, '10.3.0', f.head);
  const [candidate] = await candidates(f.github);
  assert.equal(candidate.version.toString(), '11.0.0');
  assert.match(candidate.body.toString(), /BREAKING CHANGES/);
  assert.match(candidate.body.toString(), /move public modules/);
  assert.match(candidate.body.toString(), /1811/);
  assert.doesNotMatch(candidate.body.toString(), /previous release content/);
});

for (const [message, version] of [
  ['feat: add a feature', '10.4.0'],
  ['fix: fix a defect', '10.3.1'],
  ['refactor: rearrange internals', undefined],
  ['docs: improve the guide', undefined],
  ['chore: change internals\n\nBREAKING CHANGE: remove public modules', '11.0.0'],
]) {
  test(`ancestry range preserves classification of ${message.split('\n')[0]}`, async t => {
    const f = fixture(t, message);
    useReleaseRange(f.github, f.cwd, '10.3.0', f.head);
    const result = await candidates(f.github);
    assert.equal(result[0]?.version.toString(), version);
  });
}

test('missing API commits fail before any commit is yielded', async t => {
  const f = fixture(t);
  f.commits.splice(2, 1);
  useReleaseRange(f.github, f.cwd, '10.3.0', f.head);
  const iterator = f.github.mergeCommitIterator('main');
  await assert.rejects(iterator.next(), /Incomplete release history/);
});

test('PR overrides and metadata survive and released ancestors are excluded', async t => {
  const f = fixture(t);
  f.commits[2].pullRequest = {body: 'BEGIN_COMMIT_OVERRIDE\nfeat!: replace API\nEND_COMMIT_OVERRIDE'};
  useReleaseRange(f.github, f.cwd, '10.3.0', f.head);
  const result = await Array.fromAsync(f.github.mergeCommitIterator('main'));
  assert.deepEqual(result.map(commit => commit.sha), [f.head, f.breaking, f.base]);
  assert.equal(result[1], f.commits[2]);
  assert.equal((await candidates(f.github))[0].version.toString(), '11.0.0');
});

test('missing tags and an insufficient search depth fail closed', async t => {
  const f = fixture(t);
  assert.throws(() => useReleaseRange(f.github, f.cwd, '10.2.0', f.head));
  useReleaseRange(f.github, f.cwd, '10.3.0', f.head);
  await assert.rejects(f.github.mergeCommitIterator('main', {maxResults: 1}).next(), /search depth/);
});


test('invalid version, SHA, branch, and a non-ancestor tag are refused', async t => {
  const f = fixture(t);
  assert.throws(() => useReleaseRange(f.github, f.cwd, '10.3.0;bad', f.head), /stable manifest/);
  assert.throws(() => useReleaseRange(f.github, f.cwd, '10.3.0', '--all'), /exact head/);
  assert.throws(() => useReleaseRange(f.github, f.cwd, '10.3.0', f.breaking));
  useReleaseRange(f.github, f.cwd, '10.3.0', f.head);
  await assert.rejects(f.github.mergeCommitIterator('dev').next(), /bound to main/);
});

test('an empty ancestry range contains only the release boundary', async t => {
  const f = fixture(t);
  useReleaseRange(f.github, f.cwd, '10.3.0', f.base);
  assert.deepEqual((await Array.fromAsync(f.github.mergeCommitIterator('main'))).map(c => c.sha), [f.base]);
});

for (const moved of [false, true]) {
  test(`release PR writes recheck main (advanced=${moved})`, async t => {
    const f = fixture(t);
    let writes = 0;
    f.github.createPullRequest = async () => { writes++; };
    f.github.updatePullRequest = async () => { writes++; };
    t.mock.method(Manifest, 'fromManifest', async () => ({
      repositoryConfig: {'.': {}}, releasedVersions: {'.': {toString: () => '10.3.0'}},
      async createPullRequests() {
        if (moved) f.commit('fix: subsequent push', '2026-11-03T00:00:00Z');
        await f.github.createPullRequest();
        await f.github.updatePullRequest();
      },
    }));
    if (moved) await assert.rejects(maintainReleasePr(f.github, f.cwd, f.head), /Main advanced/);
    else await maintainReleasePr(f.github, f.cwd, f.head);
    assert.equal(writes, moved ? 0 : 2);
  });
}

test('a moved main and mismatched manifest fail before release PR maintenance', async t => {
  const f = fixture(t);
  await assert.rejects(maintainReleasePr(f.github, f.cwd, f.base), /Main advanced/);
  t.mock.method(Manifest, 'fromManifest', async () => ({
    repositoryConfig: {'other': {}}, releasedVersions: {},
  }));
  await assert.rejects(maintainReleasePr(f.github, f.cwd, f.head), /single root package/);
});
