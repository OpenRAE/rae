# Package and artifact management decision matrix

## Evaluation method

The criteria come from #1168 and the [repository inventory](inventory.md).
The entries are qualitative architectural judgments, not vendor benchmarks,
procurement scores, or claims that an untested product configuration complies.
Product features were checked against primary documentation on 2026-09-05.
License, edition, deployment and capacity details must be confirmed when an
operator selects a concrete service.

No single class satisfies every requirement. An option that requires private
credentials for public PRs or substitutes server-provided hashes for reviewed
integrity authority is disqualified regardless of convenience.

## Common-criteria comparison

| Criterion | Repository/proxy manager: Artifactory, Nexus, Cloudsmith class | Declarative CLI manager: Aqua, Hermit class | OCI registry/artifacts | Maintained setup actions and native package managers | Direct pinned acquisition with hosted/local caches |
|---|---|---|---|---|---|
| Coverage | Python, generic and OCI support depends on product/edition; central intake and distribution | Developer executables and environment manifests; not Python's full project/build resolver or release publication | Images and arbitrary blobs; Python requires an additional Simple API/wheelhouse interface | Actions cover CI; apt/native tools cover OS/runtime dependencies; uneven upstream CLI versions | Small enumerated archive/data set; delegate Python and OCI to their native clients |
| Integrity authority | Client must retain reviewed hashes/producer policy; a repository can curate but does not establish approval merely by caching | Reviewed manifests/checksum files can govern tool bytes; registry and automatic-update defaults also need review | Digest addresses bytes; tags are mutable selectors, signatures/attestations need identity policy | Full action source SHAs plus payload policy; signed OS metadata delegates trust to distro roots | Reviewed per-platform raw and installed hashes, local admission; never fetch checksum authority at install time |
| Upstream outage/removal | Retained promoted content supports outages; an unseeded pull-through cache does not | Warm installs/bundles help; manifest lookup, bootstrap and cache misses can still contact upstream | Retained image/blob graph survives upstream loss; missing layers/referrers still break closure | Hosted tool caches and OS mirrors help; moving runner images and third-party action dependencies remain external | Warm cache helps transient outages only; durability requires promoted raw objects and backups |
| Public/fork access | Anonymous public repository or separate public path required; enterprise credentials prohibited | Public tool sources fit forks; private registries require a separate trusted context | Anonymous public pulls possible; isolated write credentials and rate limits still matter | Familiar public CI/local path; action/token permissions and runner isolation require review | Credential-free public origin/replica path; authenticated enterprise profile isolated |
| Offline/import/export | Seed all artifacts and native metadata, export supported repositories, verify after restore; service alone is not an air gap | Hermit offers bundles; Aqua checksum lock controls hashes but full offline closure must be qualified | OCI layouts enable image export; all architectures and associated evidence must travel | Native repositories/snapshots can be imported; GitHub Actions still depend on the control plane | Explicit raw-object bundle, wheelhouse, OS snapshot and bootstrap kit; cache directories alone are insufficient |
| Concurrency/high load | Commodity service concurrency, quotas, observability; operator capacity/HA work | Client-specific locking/cache behavior needs adversarial qualification | Blob deduplication helps; service/daemon contention and GC require operations | Runner isolation and native package locks; concurrent test resource names remain repo work | Private temp paths, digest-scoped locks/atomic installs; share immutable seeds, not writable multi-user caches |
| Portability | Server platform independent of clients, format/client availability still constrained | Platform coverage per manifest; Linux/macOS is not a promise for every package | Per-platform image graphs; registry architecture does not imply host daemon capability | Linux/macOS packages differ; GitHub workflow and local paths require equivalence tests | Explicit four-platform CLI table and Linux x86_64-only proof profile; unsupported targets fail before fetch |
| Bootstrap trust | Trust host, service deployment, CA, credentials and client; manager cannot bootstrap trust in itself | Adds manager binary, registry, shims/proxies and update policy to the trusted closure | Adds registry client, auth and possibly daemon; cannot obtain client only from itself | OS/vendor or runner-image roots are explicit starting points; action pin is separate from fetched binary pin | OS-supplied qualified curl and hashing tools fetch pinned uv/other bootstrap bytes; no remote script execution |
| Operations/security | Strong fit for mirror-only policy, retention and auditing; ACLs, quarantine, backups, upgrades and DR are operator duties | Good developer ergonomics; not an artifact promotion/retention/revocation service | Good immutable storage primitive; quarantine/status/backup/referrer retention must be supplied | Upstream owns transports; limited unified lifecycle and outage ownership | Low service burden initially; curated set must stay small, local admission code still needs maintenance |
| Cost and maintenance | Service/edition cost, operational staffing and capacity; no price assumed | Additional client/manifest ecosystem, package definitions and qualification; can reduce installer code | Storage/egress plus registry operation; conversion/export tooling adds maintenance | Small repo integration cost; external platform lifecycle and supply-chain dependence | Small native-client invocation surface; becomes unattractive if it grows into dependency solving or many package formats |
| Decision | Conforming optional enterprise distribution provider; no mandatory vendor | Evaluated, not selected as a required client now | Selected for test images and portable image storage/export | Selected for CI orchestration and OS/bootstrap | Selected only for curated non-Python archives/data, backed by retained promoted objects |

## Product evidence and limits

Artifactory distinguishes an on-demand proxy cache from a mirror; uncached
artifacts are not available merely because a remote is configured. Its
remote controls include offline and metadata/cache behavior. Nexus separates
proxy, hosted and group repositories. These support the architecture's
distinction between intake cache and retained promoted storage.
[Artifactory remote repositories](https://docs.jfrog.com/artifactory/docs/remote-repositories),
[Nexus repository types](https://help.sonatype.com/en/repository-types.html).

Cloudsmith documents upstream proxying/caching for supported formats. This is
a distribution mechanism; its suitability for an enterprise profile still
requires format, policy, export and retention qualification.
[Cloudsmith upstreams](https://docs.cloudsmith.com/repositories/upstreams).

Aqua supports a committed checksum file and requires explicit configuration
to enforce missing-checksum failure; registry policy controls another trust
surface. Hermit manifests can carry platform hashes and mirrors, and Hermit
can bundle an environment. These are credible alternatives if the curated
tool set grows; neither fact proves the complete repository runs offline.
[Aqua checksums](https://aquaproj.github.io/docs/reference/config/checksum/),
[Aqua registry policy](https://aquaproj.github.io/docs/guides/policy-as-code/),
[Hermit manifests](https://cashapp.github.io/hermit/packaging/schema/manifest/),
[Hermit bundles](https://cashapp.github.io/hermit/usage/bundle/).

OCI defines digest-addressed blobs and manifests, mutable tags, and references
between content. Skopeo provides image copy options including all-platform
copy and digest preservation. These support image mirroring/export, but an
export must still test that its entire selected graph is present.
[OCI distribution specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md),
[Skopeo copy reference](https://github.com/podman-container-tools/skopeo/blob/main/docs/skopeo-copy.1.md).

GitHub recommends full-length commit pins for immutable action selection.
That source pin does not qualify arbitrary downloads made by the action.
Native managers and setup actions remain appropriate within an explicitly
reviewed bootstrap profile.
[GitHub secure use reference](https://docs.github.com/en/actions/reference/security/secure-use).

uv documents concurrent cache use and supported cache maintenance. Its build
documentation provides hashed build constraints; a project lock alone is not
the complete isolated-build policy. Keep these capabilities in the maintained
Python client instead of implementing another resolver.
[uv cache safety](https://docs.astral.sh/uv/concepts/cache/#cache-safety),
[uv build constraints](https://docs.astral.sh/uv/concepts/projects/build/).

curl supplies HTTP handling, retry controls and transfer limits. Option
semantics depend on the qualified version: for example, unknown-length size
enforcement changed in 8.4.0, and its retry time limit is not a strict total
wall deadline. Repository code must not attempt to repair protocol behavior;
use a supported client build plus process/resource limits.
[curl command reference](https://curl.se/docs/manpage.html).

## Selected composition and reconsideration triggers

Select **uv + maintained setup/native bootstrap + generic HTTPS for curated
raw objects + OCI for images**, with reviewed integrity authority and an
optional enterprise repository provider. The public profile uses official
origins and a promoted public replica when provisioned; enterprise and
disconnected profiles use the same hashes with their own approved storage.
Python Simple API and generic HTTPS keep common installation independent of
an OCI-specific adapter. The storage interface is selected now; no unowned
service endpoint or unverified vendor deployment is claimed to exist.

Direct raw acquisition is justified for Conftest, Gitleaks, Vale, OSV Scanner,
Isabelle and the five governed vocabulary source snapshots because they have no
shared dependency resolution problem and need different execution/sandbox behavior.
It may perform selection and local admission but cannot grow a resolver,
plugin ecosystem or HTTP service. Intake manifests must make every exception
visible. A new dependency graph, repeated complex package extraction, a second
generic installation strategy, or material client-support burden requires
revisiting Aqua/Hermit before extending repository installer code.

Choose a concrete repository service only when an owner provides a tested
deployment satisfying the mirror-only, backup/restore, quota and export
acceptance cases. That deployment decision cannot weaken ADR-106/107. A change
to integrity authority, public credential requirements or the no-custom-HTTP
rule requires an ADR, not a provider configuration change.
