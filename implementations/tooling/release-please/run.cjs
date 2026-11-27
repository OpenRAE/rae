'use strict';

const {execFileSync} = require('node:child_process');
const {readFileSync} = require('node:fs');
const {GitHub, Manifest} = require('release-please');

function git(cwd, ...args) {
  return execFileSync('git', args, {cwd, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024}).trim();
}

// Keep upstream commit objects (including PR overrides), but select by ancestry.
// Buffer before yielding so a truncated API response cannot produce partial notes.
function useReleaseRange(github, cwd, version, head) {
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version) ||
      !/^[a-f0-9]{40}$/.test(head)) {
    throw new Error('Expected a stable manifest version and an exact head SHA');
  }
  const base = git(cwd, 'rev-parse', '--verify', `refs/tags/v${version}^{commit}`);
  git(cwd, 'merge-base', '--is-ancestor', base, head);
  const range = git(cwd, 'rev-list', '--topo-order', `${base}..${head}`);
  const selected = [...(range ? range.split('\n') : []), base];
  const original = github.mergeCommitIterator.bind(github);
  github.mergeCommitIterator = async function* (branch, options = {}) {
    if (branch !== 'main') throw new Error('Release range is bound to main');
    const limit = options.maxResults ?? 500;
    if (selected.length > limit) throw new Error('Release range exceeds the commit search depth');
    const missing = new Set(selected);
    const found = new Map();
    for await (const commit of original(branch, {...options, maxResults: limit})) {
      if (missing.delete(commit.sha)) found.set(commit.sha, commit);
      if (missing.size === 0) break;
    }
    if (missing.size) throw new Error(`Incomplete release history: ${missing.size} commits missing`);
    for (const sha of selected) yield found.get(sha);
  };
}

async function maintainReleasePr(github, cwd, head) {
  function checkHead() {
    const remote = git(cwd, 'ls-remote', '--exit-code', 'origin', 'refs/heads/main').split(/\s/)[0];
    if (remote !== head) throw new Error('Main advanced; run release maintenance for the current head');
  }
  checkHead();
  const version = JSON.parse(readFileSync(`${cwd}/.release-please-manifest.json`, 'utf8'))['.'];
  useReleaseRange(github, cwd, version, head);
  const manifest = await Manifest.fromManifest(github, 'main');
  if (Object.keys(manifest.repositoryConfig).join() !== '.' ||
      manifest.releasedVersions['.'].toString() !== version) {
    throw new Error('Release range requires the single root package and matching manifest version');
  }
  for (const name of ['createPullRequest', 'updatePullRequest']) {
    const original = github[name].bind(github);
    github[name] = async (...args) => {
      checkHead();
      return original(...args);
    };
  }
  await manifest.createPullRequests();
}

async function main() {
  const [owner, repo] = process.env.GITHUB_REPOSITORY.split('/');
  const github = await GitHub.create({owner, repo, token: process.env.GH_TOKEN, defaultBranch: 'main'});
  await maintainReleasePr(github, process.cwd(), process.env.GITHUB_SHA);
}

module.exports = {useReleaseRange, maintainReleasePr};
if (require.main === module) main().catch(error => {
  console.error(`Release PR maintenance failed: ${error.message}`);
  process.exitCode = 1;
});
