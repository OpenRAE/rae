# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

PRs do **not** edit this file directly. release-please maintains it from the
Conventional Commit history on `main` (#684).

## [4.0.0](https://github.com/OpenRAE/rae/compare/v3.5.0...v4.0.0) (2026-09-12)


### ⚠ BREAKING CHANGES

* **sdl:** externalize domain classifications into generic bindings ([#1243](https://github.com/OpenRAE/rae/issues/1243))

### Features

* add scoped observation demand policy ([#1245](https://github.com/OpenRAE/rae/issues/1245)) ([4914612](https://github.com/OpenRAE/rae/commit/4914612d108f06ff9db2eb69a14449a830a20848))
* add typed domain profile contracts ([#1232](https://github.com/OpenRAE/rae/issues/1232)) ([4169a94](https://github.com/OpenRAE/rae/commit/4169a94a84ab71cbb9920c789622248fa5bc1211))
* **realization:** admit prepared completions and validate delivered state ([#1251](https://github.com/OpenRAE/rae/issues/1251)) ([6e8c198](https://github.com/OpenRAE/rae/commit/6e8c198a5df07173b573b9caee8a87dc6d35262a))
* **runtime:** define control-plane operation lifecycle contract ([#1235](https://github.com/OpenRAE/rae/issues/1235)) ([190b305](https://github.com/OpenRAE/rae/commit/190b305f900cbff582b0bb941ef3b5a557b3e119))
* **runtime:** enforce capture admission and evidence proof ([#1239](https://github.com/OpenRAE/rae/issues/1239)) ([68d25df](https://github.com/OpenRAE/rae/commit/68d25df06a33a0f60224c7e0aa6fe8026fbe4a58))
* **sdl:** add recursive realization constraint normal form ([#1233](https://github.com/OpenRAE/rae/issues/1233)) ([161221b](https://github.com/OpenRAE/rae/commit/161221b4e2b4e0e2f8ba3968aaf9114adf58a6a9))
* **sdl:** externalize domain classifications into generic bindings ([#1243](https://github.com/OpenRAE/rae/issues/1243)) ([476df8c](https://github.com/OpenRAE/rae/commit/476df8cd7e76b3bf9bae485cfd62f1e3c955b463))


### Bug Fixes

* preserve exact constraints in mixed runtime realization ([#1214](https://github.com/OpenRAE/rae/issues/1214)) ([5d2f738](https://github.com/OpenRAE/rae/commit/5d2f738fb137760480a3ef9b2eae023f5df1c65b))
* **quality:** clear control-plane Sonar findings ([#1252](https://github.com/OpenRAE/rae/issues/1252)) ([956a266](https://github.com/OpenRAE/rae/commit/956a266f775485e3599195fc058e6f4af858b2ca))
* **quality:** clear the dev new-code violations blocking the Sonar gate ([#1255](https://github.com/OpenRAE/rae/issues/1255)) ([c899612](https://github.com/OpenRAE/rae/commit/c899612298f8d061e4e864c9b67b6fde2b913da0))
* **quality:** clear the dev-to-main promotion Sonar violations ([#1260](https://github.com/OpenRAE/rae/issues/1260)) ([106b195](https://github.com/OpenRAE/rae/commit/106b195e3dc0048a647e845876e8eaefe08e3d1b))
* **runtime:** add snapshot revision compare-and-swap ([#1240](https://github.com/OpenRAE/rae/issues/1240)) ([f834682](https://github.com/OpenRAE/rae/commit/f8346828bde8ddce0db4c273d76bc439ac650134))
* **runtime:** make local operation state transactional and durable ([#1136](https://github.com/OpenRAE/rae/issues/1136)) ([ca26076](https://github.com/OpenRAE/rae/commit/ca26076cf275c9c6adff3afe3d157e4b45c09a50))
* **runtime:** seal reconciled operations after uncertain commits ([#1231](https://github.com/OpenRAE/rae/issues/1231)) ([fb4cb4b](https://github.com/OpenRAE/rae/commit/fb4cb4b7002305e7062bc51f1eda77c5852b2642))
* **runtime:** unify control-plane mutation commits ([#1248](https://github.com/OpenRAE/rae/issues/1248)) ([d67d320](https://github.com/OpenRAE/rae/commit/d67d320559f2f91cd991a9511052db1085e0b9c4))
* **tooling:** use maintained client for tool acquisition ([#1246](https://github.com/OpenRAE/rae/issues/1246)) ([8e6dbb7](https://github.com/OpenRAE/rae/commit/8e6dbb742fb98d50bb16a55c47f941abd49ff58d))


### Documentation

* define modular participant control and governed effects ([#1234](https://github.com/OpenRAE/rae/issues/1234)) ([ebb70a3](https://github.com/OpenRAE/rae/commit/ebb70a34b8e7d1cc8964c443841ae57e12ed1014)), closes [#1068](https://github.com/OpenRAE/rae/issues/1068)
* define recursive partial-description semantics ([#1215](https://github.com/OpenRAE/rae/issues/1215)) ([8dc823b](https://github.com/OpenRAE/rae/commit/8dc823bab555f4f04ec83a0eec38d6101c2adfed))
* **sdl:** document progressive specification design review ([#1213](https://github.com/OpenRAE/rae/issues/1213)) ([164dd14](https://github.com/OpenRAE/rae/commit/164dd140731a20506690140b7133d526257a1156))
* **sdl:** record issue 1198 design review and remediation plan ([164dd14](https://github.com/OpenRAE/rae/commit/164dd140731a20506690140b7133d526257a1156))
* **tooling:** define package and artifact management architecture ([#1229](https://github.com/OpenRAE/rae/issues/1229)) ([c3b30c6](https://github.com/OpenRAE/rae/commit/c3b30c6caf7d99afb66675e42290ae1ff15f6b24))

## [3.5.0](https://github.com/OpenRAE/rae/compare/v3.4.0...v3.5.0) (2026-09-04)


### Features

* complete runtime configuration boundary coverage ([#1178](https://github.com/OpenRAE/rae/issues/1178)) ([de9bbd6](https://github.com/OpenRAE/rae/commit/de9bbd629dec7b6b274444c90f452149c45092f9))
* **sdl:** add typed package repository profiles ([#1194](https://github.com/OpenRAE/rae/issues/1194)) ([208f31f](https://github.com/OpenRAE/rae/commit/208f31fa401fd7bf9127a5fb11c8e2fa09e93b16))


### Bug Fixes

* allow draft release inspection ([#1192](https://github.com/OpenRAE/rae/issues/1192)) ([ce68fbc](https://github.com/OpenRAE/rae/commit/ce68fbc9a207a7b2e24c6d70466a1a53bdfa9816))
* **libvirt:** harden failure observability ([#1191](https://github.com/OpenRAE/rae/issues/1191)) ([635825a](https://github.com/OpenRAE/rae/commit/635825a15a4dfe78a6aac4596097f2e7adf44dde))


### Documentation

* **runtime:** define control-plane architecture ([#1193](https://github.com/OpenRAE/rae/issues/1193)) ([9bca203](https://github.com/OpenRAE/rae/commit/9bca203f94475824a31ad2255765a4c57e953e95))

## [3.4.0](https://github.com/OpenRAE/rae/compare/v3.3.0...v3.4.0) (2026-09-03)


### Features

* add semantic projection reports ([#1079](https://github.com/OpenRAE/rae/issues/1079)) ([8283fa5](https://github.com/OpenRAE/rae/commit/8283fa5670ca1f330f75f1f598aee5406c4f0fa1))
* add source-neutral SDL candidate synthesis ([#1113](https://github.com/OpenRAE/rae/issues/1113)) ([48748ee](https://github.com/OpenRAE/rae/commit/48748eed31af1886b3c6a3d002c93e17adf37b5e))
* add target-node CPU architecture semantics to SDL ([#1056](https://github.com/OpenRAE/rae/issues/1056)) ([2e4aabb](https://github.com/OpenRAE/rae/commit/2e4aabb0cdb5009873f8170cbd8bc2e5abfa63ca))
* carry authored OS identity through realization ([#1141](https://github.com/OpenRAE/rae/issues/1141)) ([7b73821](https://github.com/OpenRAE/rae/commit/7b73821c470a9ff60c493b78c830f406c0aa776d))
* carry resolved realization authority through plans ([#1081](https://github.com/OpenRAE/rae/issues/1081)) ([5c210d5](https://github.com/OpenRAE/rae/commit/5c210d520e884cca0c08ad201b033fae920ce0c2))
* define account fixture credential semantics ([#1073](https://github.com/OpenRAE/rae/issues/1073)) ([0248946](https://github.com/OpenRAE/rae/commit/02489463a85d6af88ebcdf469b719f8645d40cbf))
* enforce participant flow policy at final runtime sinks ([#1058](https://github.com/OpenRAE/rae/issues/1058)) ([6b47385](https://github.com/OpenRAE/rae/commit/6b47385f03d9bb682761f2b8c55c57ae411a80a2))
* **examples:** add the canonical minimal cross-backend scenario ([#1149](https://github.com/OpenRAE/rae/issues/1149)) ([789e7b5](https://github.com/OpenRAE/rae/commit/789e7b5177711056425a8e09894b22c72b804dc8))
* govern portable runtime process limits ([#1080](https://github.com/OpenRAE/rae/issues/1080)) ([0e30b38](https://github.com/OpenRAE/rae/commit/0e30b388486448dd5f1cff7a8b57231f0938bbf7))
* publish adversarial participant flow-control contracts ([#1053](https://github.com/OpenRAE/rae/issues/1053)) ([7159012](https://github.com/OpenRAE/rae/commit/71590121d30d920be2714a82a035b8821a018413))
* **runtime:** declare adversarial-control apparatus and backend capabilities (API-407) ([#1062](https://github.com/OpenRAE/rae/issues/1062)) ([021dc7a](https://github.com/OpenRAE/rae/commit/021dc7a28313dfc5d6e52f1c92754e8117119350))
* **sdl:** define participant episode termination semantics and RL closure record (SEM-222) ([#1059](https://github.com/OpenRAE/rae/issues/1059)) ([1fdb85b](https://github.com/OpenRAE/rae/commit/1fdb85b73b2b811935e74ff73884c161559bb17d))
* separate compute kind from realization substrate ([#1082](https://github.com/OpenRAE/rae/issues/1082)) ([3d6e369](https://github.com/OpenRAE/rae/commit/3d6e369b726607ff657a841c7f1dee0bec655b8f))


### Bug Fixes

* **conformance:** keep the default adapter probe envelope-neutral ([#1159](https://github.com/OpenRAE/rae/issues/1159)) ([e014281](https://github.com/OpenRAE/rae/commit/e0142812e09f68f4b4066d986210e888c3a0ac78))
* **contracts:** admit expanded scenario snapshot parents ([#1040](https://github.com/OpenRAE/rae/issues/1040)) ([#1123](https://github.com/OpenRAE/rae/issues/1123)) ([14bfc7b](https://github.com/OpenRAE/rae/commit/14bfc7b28eb9817482a2439778ba699f9d4a47e4))
* harden repo-policy governance check timeout, host, and status reporting ([#1060](https://github.com/OpenRAE/rae/issues/1060)) ([92e6e23](https://github.com/OpenRAE/rae/commit/92e6e23d19b73f5470769e7fc8013b715ed68e1c))
* **libvirt:** bind reproducible guest operations to fresh evidence ([#1128](https://github.com/OpenRAE/rae/issues/1128)) ([1a38538](https://github.com/OpenRAE/rae/commit/1a38538c26abbbca0adf6ec4c56d004cc9ce743a))
* **libvirt:** record suppressed native failures on the operator side ([#1163](https://github.com/OpenRAE/rae/issues/1163)) ([3b853a3](https://github.com/OpenRAE/rae/commit/3b853a3423f0b19a633d3977b4725c49aafec1f0))
* **module-registry:** harden OCI publication and caching ([#1130](https://github.com/OpenRAE/rae/issues/1130)) ([15e6118](https://github.com/OpenRAE/rae/commit/15e61189f68fd257a85692376c8b99ee3504a30d))
* **processor:** bound dependency-cycle detection ([#1103](https://github.com/OpenRAE/rae/issues/1103)) ([d4b4432](https://github.com/OpenRAE/rae/commit/d4b4432ee38ce13bd07cafe4e624c7d364ea9f8a))
* **processor:** bound dependency-cycle detection ([#1126](https://github.com/OpenRAE/rae/issues/1126)) ([d4b4432](https://github.com/OpenRAE/rae/commit/d4b4432ee38ce13bd07cafe4e624c7d364ea9f8a))
* **processor:** bound the complete solver operation ([#1108](https://github.com/OpenRAE/rae/issues/1108)) ([#1127](https://github.com/OpenRAE/rae/issues/1127)) ([e4612cf](https://github.com/OpenRAE/rae/commit/e4612cf3bc4a8ebc73f004bf6a2d5849966dc01d))
* **processor:** enforce evaluator capability admission ([#1036](https://github.com/OpenRAE/rae/issues/1036)) ([#1119](https://github.com/OpenRAE/rae/issues/1119)) ([f005152](https://github.com/OpenRAE/rae/commit/f005152f7cae5328ddd15f4f1e0f09519a389ad3))
* **processor:** enforce solver deadline boundaries ([#1142](https://github.com/OpenRAE/rae/issues/1142)) ([eacfc46](https://github.com/OpenRAE/rae/commit/eacfc46f5901eb72c6cd01808a16c3bef839efc8))
* **proof:** make offline Isabelle replay portable on Ubuntu ([#1131](https://github.com/OpenRAE/rae/issues/1131)) ([990e8fb](https://github.com/OpenRAE/rae/commit/990e8fbc246769fd95f4100e225a2eb69e2812f3))
* **reference-backend:** anchor the OCI digest-pinned image-trust check ([#1084](https://github.com/OpenRAE/rae/issues/1084)) ([83c3651](https://github.com/OpenRAE/rae/commit/83c36513f464c51e3451f83be4a722e595a8e841))
* **release:** gate publication on the verified release SHA ([#1138](https://github.com/OpenRAE/rae/issues/1138)) ([701858d](https://github.com/OpenRAE/rae/commit/701858d190d7996d196dbfca79cfd1d9a715cebf))
* **runtime:** harden HTTP API admission and offload ([#1133](https://github.com/OpenRAE/rae/issues/1133)) ([944b461](https://github.com/OpenRAE/rae/commit/944b4617ab96c544c2ce15ee46a93cf0431ff346))
* **runtime:** reconcile workflow timeouts fail closed ([#1132](https://github.com/OpenRAE/rae/issues/1132)) ([96b20ae](https://github.com/OpenRAE/rae/commit/96b20ae8422fae9936bae928bbd8a1c14d2001da))
* **runtime:** settle concurrent participant batches reliably ([#1135](https://github.com/OpenRAE/rae/issues/1135)) ([2d53aa3](https://github.com/OpenRAE/rae/commit/2d53aa34fbbc8faa4617320bd8d7f0d1042d5e24))
* **runtime:** synchronize operational summary reads ([#1148](https://github.com/OpenRAE/rae/issues/1148)) ([915b0c0](https://github.com/OpenRAE/rae/commit/915b0c002b86e8f59a95f0409b412bd7be57695d))
* **supply-chain:** gate vulnerable dependencies and scanner cache ([#1121](https://github.com/OpenRAE/rae/issues/1121)) ([0f296b9](https://github.com/OpenRAE/rae/commit/0f296b956e7656f48ce27cd25b4aa13bc1a4491a))


### Performance Improvements

* **cli:** bypass command imports for exact version ([#1111](https://github.com/OpenRAE/rae/issues/1111)) ([3cd0f49](https://github.com/OpenRAE/rae/commit/3cd0f49f85b0c2429ba8eda680d16b4dd2d37499))
* **cli:** bypass command imports for exact version ([#1129](https://github.com/OpenRAE/rae/issues/1129)) ([3cd0f49](https://github.com/OpenRAE/rae/commit/3cd0f49f85b0c2429ba8eda680d16b4dd2d37499))
* **processor:** materialize explicitness once per compile ([#1099](https://github.com/OpenRAE/rae/issues/1099)) ([6fb2820](https://github.com/OpenRAE/rae/commit/6fb28200cf0970e7af268edc5de27b101f3e545b))
* **processor:** materialize explicitness once per compile ([#1120](https://github.com/OpenRAE/rae/issues/1120)) ([6fb2820](https://github.com/OpenRAE/rae/commit/6fb28200cf0970e7af268edc5de27b101f3e545b))


### Documentation

* add Ground Control requirement specs as repo-local files ([#1064](https://github.com/OpenRAE/rae/issues/1064)) ([771756f](https://github.com/OpenRAE/rae/commit/771756f675e2666328b6a926c64d5d77e6e90e9f))
* joint design for participant episode + budget model (SEM-222/223, DSL-120/121, ACT-623/624) ([#1055](https://github.com/OpenRAE/rae/issues/1055)) ([645ef61](https://github.com/OpenRAE/rae/commit/645ef61f382cc7e69538b2fd4e643a96366bc98e))

## [3.3.0](https://github.com/OpenRAE/rae/compare/v3.2.0...v3.3.0) (2026-08-02)


### Features

* add dynamic participant information state ([eaa0939](https://github.com/OpenRAE/rae/commit/eaa0939047a1d519fb2e1207ec873af8b5cc5fc0))
* add planned resource payload accessors ([f6eda51](https://github.com/OpenRAE/rae/commit/f6eda5122e65a6a18c47d83cb1a97296f703f575))
* add planned resource payload accessors ([472bd56](https://github.com/OpenRAE/rae/commit/472bd56950621ae9c5bfcebf69d462e1bd23a94b))
* add safe artifact transformations ([c5da811](https://github.com/OpenRAE/rae/commit/c5da811f8e306fbfa7b86006361d75ce3b3380e3))
* declare backend participant opacity realization ([5f87c0a](https://github.com/OpenRAE/rae/commit/5f87c0a14ade8cc5cce6dc69931c35bf320e3a50))
* define forwarding-agent realization semantics ([e1f9885](https://github.com/OpenRAE/rae/commit/e1f98856df71a5228579d5de18d3385faa67c473))
* define forwarding-agent realization semantics ([4dd8a46](https://github.com/OpenRAE/rae/commit/4dd8a4641e04f46b83f84055742ba9171d367df7))
* **runtime:** enforce bounded participant opacity ([58ae48b](https://github.com/OpenRAE/rae/commit/58ae48b32ba8307b25d884a894b2592f5d116aec))


### Bug Fixes

* apply backend protocol Any-signature policy to every protocol module ([3e38aa3](https://github.com/OpenRAE/rae/commit/3e38aa3b00cddd6313cdc06c3f05afc0f1ae3a80))
* apply backend protocol Any-signature policy to every protocol module ([eb6f295](https://github.com/OpenRAE/rae/commit/eb6f295ac248c649b460cbd6601132842cd4a17b))
* reduce realization helper complexity ([179827b](https://github.com/OpenRAE/rae/commit/179827b2029f3aac78ef0a8068e1f0d0f575184f))
* repair oversized allowlist after dev merge (drop stale split-file entries) ([d8dfdcb](https://github.com/OpenRAE/rae/commit/d8dfdcb4b295022cde5d77ea6d9889d114f1bf8b))
* simplify libvirt network realization ([c7c2dd4](https://github.com/OpenRAE/rae/commit/c7c2dd4f8321f688e01f704be84225f7534cffd0))


### Documentation

* reconcile ACT-605 behavior profile coverage ([8b99260](https://github.com/OpenRAE/rae/commit/8b992607a5149058823225d7b29cf674f5eaede1))
* reconcile ACT-605 behavior profile coverage ([110f934](https://github.com/OpenRAE/rae/commit/110f934f7db4c15c35dbe04048b4c85a6f78a217))

## [3.2.0](https://github.com/OpenRAE/rae/compare/v3.1.0...v3.2.0) (2026-07-31)


### Features

* add autonomous behavior vocabulary bindings ([b611e34](https://github.com/OpenRAE/rae/commit/b611e34e19be453cdd90959e41cf024780416e05))
* add portable search-index schema materialization ([08d03a6](https://github.com/OpenRAE/rae/commit/08d03a66f7b8db7e59d02c7da9f64cbbf0eb2f66))
* add portable search-index schema materialization ([54654ab](https://github.com/OpenRAE/rae/commit/54654ab81141801806fc2201b362f78449167a30))
* **cli:** add human semantic operations ([020db55](https://github.com/OpenRAE/rae/commit/020db559007a3a97577483b3e56771e2c4de8a52))
* **cli:** add human semantic operations ([853a847](https://github.com/OpenRAE/rae/commit/853a8470ed1a508b483fae93b7c3b32fb58a8d78))
* **formal:** prove participant opacity and accelerate verification ([58342ec](https://github.com/OpenRAE/rae/commit/58342ece6aa67aa5632314b3936ee400e6bc8792))
* **sdl:** add isolated SSH generated artifacts ([7a39cfc](https://github.com/OpenRAE/rae/commit/7a39cfc6a113e93c32e98196d78d3f3c6885749c))
* **sdl:** add isolated SSH generated artifacts ([6d1c8d1](https://github.com/OpenRAE/rae/commit/6d1c8d12bc8886507f54c29091498c20d86218b2))


### Bug Fixes

* address SonarCloud findings ([a673fa0](https://github.com/OpenRAE/rae/commit/a673fa0d2a13111988f1769a200412a1eba465da))
* **contracts:** align capability schema defaults ([d91cf62](https://github.com/OpenRAE/rae/commit/d91cf62c669c62fefd79827475629b781fbe5cd3))
* **contracts:** remove trailing coverage pragma ([1e1ae0e](https://github.com/OpenRAE/rae/commit/1e1ae0eb648c686bbe401529b51e0fe70c62bd02))
* **sdl:** address SSH artifact quality findings ([38d9e8f](https://github.com/OpenRAE/rae/commit/38d9e8f16fbf2c024a7639b23ee1dc905cd5c2e2))
* **sdl:** preserve omitted output selections ([e3cfb6d](https://github.com/OpenRAE/rae/commit/e3cfb6d3dc364b12c2f5c14030f0f4efc0f5f7b3))
* **sdl:** reduce content validator complexity ([b1368cd](https://github.com/OpenRAE/rae/commit/b1368cd4d00306314e8c99fbbb8fa01824d4cb9f))
* **sdl:** reduce content validator complexity ([f65e339](https://github.com/OpenRAE/rae/commit/f65e339e83b9724643ce5359ed7abc67ba3fe902))


### Documentation

* define adversarial participant control program ([675b61f](https://github.com/OpenRAE/rae/commit/675b61f4ae9e0ff5648f75e142e91e546e1dbbb7))
* define mixed cross-backend participant control ([a9914f3](https://github.com/OpenRAE/rae/commit/a9914f3755e55bd14b8c21c720c5ea28e6c438a0))

## [3.1.0](https://github.com/RAESystem/rae/compare/v3.0.0...v3.1.0) (2026-07-30)


### Features

* add governed adaptive difficulty policies ([7b00b56](https://github.com/RAESystem/rae/commit/7b00b569a70742547740788f22328061df0c3e53))
* add governed adaptive difficulty policies ([cbe741a](https://github.com/RAESystem/rae/commit/cbe741ad754f6377974310ac90aec371fb3da6b3))
* add portable external concept bindings ([f2ca0b5](https://github.com/RAESystem/rae/commit/f2ca0b576fab9493f622a1ccb944bf4b6883c72c))
* **formal:** define participant crossing bisimulation ([876243d](https://github.com/RAESystem/rae/commit/876243d855e79caaa52df075e8afa36c0243271f))
* implement participant opacity conformance profile ([b124151](https://github.com/RAESystem/rae/commit/b124151016778dcaf758053b2a011ee482e6e7d8))
* integrate admitted trial realization provenance ([2f9fd03](https://github.com/RAESystem/rae/commit/2f9fd037df2bfc32d0de93ffc299d832b6a070eb))
* lower runtime configuration realization concerns ([6b47d7c](https://github.com/RAESystem/rae/commit/6b47d7c2b540f142646d8975376f20d889ece5bf))
* model-check finite participant opacity profiles ([72f0e51](https://github.com/RAESystem/rae/commit/72f0e51237cd50b73535c4f2ecb7be2bcd94c866))
* publish SCE-006 isolated batch trial scheduling handoff ([6ff5314](https://github.com/RAESystem/rae/commit/6ff531451f773c198b5ba0b604746517ca26aaa4))
* publish SCE-006 isolated batch trial scheduling handoff ([98c9e44](https://github.com/RAESystem/rae/commit/98c9e44933cb50ad66567abf99f1ec1286f833a9))


### Bug Fixes

* bind adaptive observations to source definitions ([9c16601](https://github.com/RAESystem/rae/commit/9c1660174a465052866037e1927e25bfee6876fd))
* keep the tracked .codex rules file, drop its erroneous gitignore entry ([590c7c9](https://github.com/RAESystem/rae/commit/590c7c9d0c33d14f4e39203a944df86d3b44b648))
* preserve tracked skill discovery ([ffa27a8](https://github.com/RAESystem/rae/commit/ffa27a89080bef503c6aaca384dff2c0d861a54a))
* resolve SonarCloud quality gate findings ([725da3e](https://github.com/RAESystem/rae/commit/725da3e01f032277628a34c3a5293906f257450e))
* resolve SonarCloud quality gate findings ([418af1d](https://github.com/RAESystem/rae/commit/418af1da9788224b358b47156a981885f762a8d5))
* stop ignoring a tracked agent-rules file that tests read ([4368161](https://github.com/RAESystem/rae/commit/4368161012bf46c5ebd9f51c302048846d6a55a5))

## [3.0.0](https://github.com/RAESystem/rae/compare/v2.0.0...v3.0.0) (2026-07-29)


### ⚠ BREAKING CHANGES

* published schema `$id` values move from `https://raes.dev/schemas/` to `https://raesystem.github.io/rae/schemas/`. Consumers pinning or caching schema identifiers must update them.

### Features

* add bounded counterfactual necessity validation ([bde2f1c](https://github.com/RAESystem/rae/commit/bde2f1c0fd6f28833ad0380a354aa7c410274f64))
* add bounded determinism and replay-consistency verification (ASR-514) ([fa8b143](https://github.com/RAESystem/rae/commit/fa8b143de7a6b9816bef47bde6331a77b7e9fe5c))
* add bounded determinism and replay-consistency verification (ASR-514) ([cbf2b2f](https://github.com/RAESystem/rae/commit/cbf2b2f84b628ea6bf6f406ad80362d590fc2c9b))
* add deterministic trial compilation ([b2d5b1f](https://github.com/RAESystem/rae/commit/b2d5b1fc9ad4b2574adca01b3ae95aa53ee9e178))
* add executable behavioral validation probes ([84ff9b3](https://github.com/RAESystem/rae/commit/84ff9b3492d857e56743556473ca9c4e0f7176df))
* add executable behavioral validation probes ([c02cbaa](https://github.com/RAESystem/rae/commit/c02cbaa038f49d48015c85641fa28fccec663fc3))
* add experiment variation selection policies ([9738462](https://github.com/RAESystem/rae/commit/97384623834091b470596fb680539757bf4b3f10))
* add experiment variation selection policies ([3b51332](https://github.com/RAESystem/rae/commit/3b5133201c4702a1fa20f476125a9fec5c209135))
* add participant information-flow assurance probes ([8f68ee0](https://github.com/RAESystem/rae/commit/8f68ee0dad22d40886cd16e12508b688fe40e553))
* add participant information-flow assurance probes ([bb5b625](https://github.com/RAESystem/rae/commit/bb5b625aa831e113a40c6220c1cac5149fd0f23a))
* enforce participant information-flow policy ([5a36f4c](https://github.com/RAESystem/rae/commit/5a36f4c906c2ed3af98ba5690bae0e4a4bd39b58))
* enforce participant information-flow policy ([96f9cb2](https://github.com/RAESystem/rae/commit/96f9cb2f5beeea3953648ebf8fcf8f23c99d2980))
* migrate participant control compatibility ([6c7a28c](https://github.com/RAESystem/rae/commit/6c7a28c0c0baf32f97164a09755a9147ca983224))
* migrate participant control compatibility ([8bccd0d](https://github.com/RAESystem/rae/commit/8bccd0d44d764498813d3caab276cee4b01fb5b3))
* publish admitted experiment trial-plan contract (SCE-002/SCE-006) ([3e69aea](https://github.com/RAESystem/rae/commit/3e69aeae45817ef5ae9fca56eefa5f8ac625a866))
* publish admitted experiment trial-plan contract (SCE-002/SCE-006) ([ff35cf2](https://github.com/RAESystem/rae/commit/ff35cf21450b4e3cea0bd65c77b6ba77690565c8))


### Bug Fixes

* address SonarCloud findings ([d5a6a69](https://github.com/RAESystem/rae/commit/d5a6a690d2b46666ce975a5047c245229bfacdba))
* align Sonar project binding ([76edc5b](https://github.com/RAESystem/rae/commit/76edc5b85131a4efa7c2c56a8b4e9b18d43970b3))
* check commit messages, not the PR body, for breaking-change footers ([1d50049](https://github.com/RAESystem/rae/commit/1d500496a3606cb05b10d0d25d383c3d84172b3f)), closes [#908](https://github.com/RAESystem/rae/issues/908)
* construct participant evidence context explicitly ([c62310a](https://github.com/RAESystem/rae/commit/c62310aaaeb091c51118f827d33f7d75f58ae70e))
* pin bot-maintained release history by classified tail ([f9da4f7](https://github.com/RAESystem/rae/commit/f9da4f79b91bbc4f68cad97c7aa816db69ee192e)), closes [#908](https://github.com/RAESystem/rae/issues/908)
* preserve typed participant evidence context ([9b8b0c0](https://github.com/RAESystem/rae/commit/9b8b0c0430401cb87d018b6126a2e4a7d5275096))
* publish Python version classifiers for the raes distribution ([ba66ce2](https://github.com/RAESystem/rae/commit/ba66ce2b9d09df280d35ba31aec0de1bb824cfcb))
* publish Python version classifiers for the raes distribution ([9a951ad](https://github.com/RAESystem/rae/commit/9a951adbef069fa61cf272449265501d1737daaa))
* reduce behavioral relation validation complexity ([90e001b](https://github.com/RAESystem/rae/commit/90e001be04b18e2d326bb98733567b4041f958de))
* reduce behavioral relation validation complexity ([6d58475](https://github.com/RAESystem/rae/commit/6d5847560d50d5332874f904edf0db1c50b778fd))
* reduce claim binding validation complexity ([6c582f2](https://github.com/RAESystem/rae/commit/6c582f297454cda06934996b9ff0ea404a762f01))
* reduce claim binding validation complexity ([a760062](https://github.com/RAESystem/rae/commit/a760062f522040d6e3bf529b87c3ecbd11f00176))
* reject retired naming in changelog-bound PR text ([b9daa5f](https://github.com/RAESystem/rae/commit/b9daa5fa356738b1c9b6931783a48908b43a2b85)), closes [#908](https://github.com/RAESystem/rae/issues/908)
* repair PR guard bootstrap and reformat a renamed test ([1a82d14](https://github.com/RAESystem/rae/commit/1a82d14c5bf510493a06986a5a011ed148706842)), closes [#908](https://github.com/RAESystem/rae/issues/908)
* replace platform profiles with composable capabilities ([9f53baf](https://github.com/RAESystem/rae/commit/9f53bafd7f51bf6d732e683182f5c525395cad1d))
* repoint published schema namespace to a controlled URI root ([e8ae819](https://github.com/RAESystem/rae/commit/e8ae8191e8005f5f6c461cba59bdf8420c755b26)), closes [#908](https://github.com/RAESystem/rae/issues/908)
* upgrade dependencies with known vulnerabilities ([2d7c0c4](https://github.com/RAESystem/rae/commit/2d7c0c4a635c47709c9ad7453a5689d3c2693802))
* upgrade dependencies with known vulnerabilities ([e2431fa](https://github.com/RAESystem/rae/commit/e2431fa9a645b882081fd99e68ed6109c0790f4f)), closes [#941](https://github.com/RAESystem/rae/issues/941)


### Documentation

* document participant input and output control ([5bbccb9](https://github.com/RAESystem/rae/commit/5bbccb9491a9d257b2ad16ca0cfcc3b6a245409b))
* document participant input and output control ([f318ee6](https://github.com/RAESystem/rae/commit/f318ee6aad4ce3a5ef42d1b57b9f0b801c0c8ca2))

## [2.0.0](https://github.com/RAESystem/rae/compare/v1.1.0...v2.0.0) (2026-07-27)


### ⚠ BREAKING CHANGES

* define exact-cut participant decision surfaces

### Features

* add autonomous participant activity policy ([b1ab49f](https://github.com/RAESystem/rae/commit/b1ab49fcc774aee8632770ea4457bd970d121d9f))
* add participant crossing policy contracts ([94fd223](https://github.com/RAESystem/rae/commit/94fd223a5e14e38ddb5a0d14b0f7623575cccd88))
* add scoped participant resource budgets ([6d194db](https://github.com/RAESystem/rae/commit/6d194db9a3b3d55a7eb6b3bac96d07b7d7f977e1))
* add supervisory participant lifecycle ([bdd8c43](https://github.com/RAESystem/rae/commit/bdd8c43351ca9e04f42e24b52209ba129e1edd47))
* **contracts:** define authoritative experiment bindings ([957155f](https://github.com/RAESystem/rae/commit/957155f13cc5eecc06481483bf89604a08e6173a))
* declare participant policy capabilities ([4694ada](https://github.com/RAESystem/rae/commit/4694adafae755900cfb7ce89cfa3dc0c001e58ac))
* define exact-cut participant decision surfaces ([ecac57d](https://github.com/RAESystem/rae/commit/ecac57dd5331ea9e80ee010ee6fcce403102f269))
* define portable artifact requirement satisfaction ([a439a99](https://github.com/RAESystem/rae/commit/a439a99ae3723dba827239f2284c567dea75aa39))
* define portable artifact requirement satisfaction ([6cd4cef](https://github.com/RAESystem/rae/commit/6cd4cef7c693c8647cf2375143f149dae6b412c4))
* **participant:** add portable execution lifecycle control ([d8937cb](https://github.com/RAESystem/rae/commit/d8937cbf7e92356ca8678bb6a01ff88baa050531))
* **participant:** add portable execution lifecycle control ([4fcc205](https://github.com/RAESystem/rae/commit/4fcc205c0e910e43c6ca728e7e32fa5751613036))


### Bug Fixes

* correct scheduler lint errors ([848de13](https://github.com/RAESystem/rae/commit/848de13dc3385239299e8200306989657c0a55ca))
* **participant:** reconcile execution contracts with RAES cutover ([6ea3457](https://github.com/RAESystem/rae/commit/6ea34570c75d2f739eae219e45bab1cefef8aa35))
* preserve activity draw call semantics ([2f71517](https://github.com/RAESystem/rae/commit/2f7151702e0ab2446cb4ffdbfc477b9602fc040c))
* record canonical schema publication hashes ([66a86f2](https://github.com/RAESystem/rae/commit/66a86f24181976ceb5b1d6b7d9d02a1cd0fca5ae))
* reduce participant behavior complexity ([13b2375](https://github.com/RAESystem/rae/commit/13b23753ecc46da686151a3eb587e18254926257))
* reduce remaining Sonar complexity for PR 932 ([530a6b1](https://github.com/RAESystem/rae/commit/530a6b18ce5b5c9f9d2ef69e0e8121196d038362))
* refresh ADR index identity pin ([e73800a](https://github.com/RAESystem/rae/commit/e73800a30ec5827b27a4d86758a27772c814dbf3))
* refresh ADR-097 content pin ([03783c5](https://github.com/RAESystem/rae/commit/03783c5455b329eebd9e7ed4b29175e6cf13414f))
* resolve Sonar quality gate findings ([3248d68](https://github.com/RAESystem/rae/commit/3248d68faef300ad69f79d70745024bf74e35f11))
* resolve Sonar quality gate findings ([298937b](https://github.com/RAESystem/rae/commit/298937bd2817cfa402c4de269ea11f5e976f9baf))
* restore contracts facade source-size compliance ([932a447](https://github.com/RAESystem/rae/commit/932a447a9ed7f804f325a3025266642e128c0ae0))
* restore Ground Control project binding ([e40274e](https://github.com/RAESystem/rae/commit/e40274e41e2bae82e0c98d8b84afd1a933e65033))
* restore Ground Control project binding ([9b2f0dc](https://github.com/RAESystem/rae/commit/9b2f0dcf18c87585efc43848812382e3a62a6937))
* split scheduler helper modules ([18c9ab5](https://github.com/RAESystem/rae/commit/18c9ab54abab8c66f33d7582b6209c02496296fc))


### Documentation

* clarify RAES ecosystem naming boundaries ([469c93f](https://github.com/RAESystem/rae/commit/469c93fefe5a0372721662623399e7b2ff12ddf2))
* establish reader-first public documentation ([b11bc5d](https://github.com/RAESystem/rae/commit/b11bc5da8cec2d8a898a6a964c21d7bf3b4a6993))
* fix ADR-097 specification reference ([6390f4e](https://github.com/RAESystem/rae/commit/6390f4e4e994224be3f5e81947071e0f5fa188b9))
* integrate decision surface v2 references ([717ae89](https://github.com/RAESystem/rae/commit/717ae8978867e4ef4ac9fc7824d4cbea43f0210d))

## [1.1.0](https://github.com/RAESystem/rae/compare/v1.0.0...v1.1.0) (2026-07-26)


### Features

* add participant-directed inject delivery ([48cb44e](https://github.com/RAESystem/rae/commit/48cb44e4f10f359e3585c45cbb64318469477460))
* support participant action-space modes ([b7a523a](https://github.com/RAESystem/rae/commit/b7a523a810809e3e5ad38b923aebc716d86a32bd))

## [1.0.0](https://github.com/RAESystem/rae/compare/v0.25.0...v1.0.0) (2026-07-25)


### ⚠ BREAKING CHANGES

* The published SDL import namespace changes from aces_sdl to raes with no compatibility alias.

### Features

* adopt raes import namespace and system framing ([#885](https://github.com/RAESystem/rae/issues/885)) ([0366281](https://github.com/RAESystem/rae/commit/0366281e00305987ef32b1697f28a396818b378a))


### Bug Fixes

* synchronize main release ancestry into dev ([#890](https://github.com/RAESystem/rae/issues/890)) ([b87309a](https://github.com/RAESystem/rae/commit/b87309acbb616f491558d71cff869bc21f15b8d4))

## [0.25.0](https://github.com/RAESystem/rae/compare/v0.24.0...v0.25.0) (2026-07-25)


### Features

* add ASR-515 validation-basis disclosure contract ([#871](https://github.com/RAESystem/rae/issues/871)) ([1cd7362](https://github.com/RAESystem/rae/commit/1cd73624c2a2a694e428f12969bc71f0899d29d3))
* **contracts:** add participant control occurrence contracts ([#868](https://github.com/RAESystem/rae/issues/868)) ([9122de5](https://github.com/RAESystem/rae/commit/9122de5be5a961c6954a5ec501748f1a5f486c57))


### Bug Fixes

* **release:** publish package as raes ([#879](https://github.com/RAESystem/rae/issues/879)) ([dad6692](https://github.com/RAESystem/rae/commit/dad6692322eccede19d81fe424ff61d20b1a253b))

## [0.24.0](https://github.com/RAESystem/rae/compare/v0.23.1...v0.24.0) (2026-07-25)


### Features

* add defensive behavior vocabularies ([#843](https://github.com/RAESystem/rae/issues/843)) ([ced4a42](https://github.com/RAESystem/rae/commit/ced4a42cde890614f16611c940dcad7643f3c426))
* add EXP-718 controlled-randomness random-stream suite ([#850](https://github.com/RAESystem/rae/issues/850)) ([4043ecc](https://github.com/RAESystem/rae/commit/4043ecc6bb345645a736243d9e29ae530bfef099))
* add formal semantic validation evidence gate ([#822](https://github.com/RAESystem/rae/issues/822)) ([24e3a32](https://github.com/RAESystem/rae/commit/24e3a323b885c7684181da9c78b95063cdf662b6))
* add goal-oriented flexible scenario steps ([#851](https://github.com/RAESystem/rae/issues/851)) ([5a8b97a](https://github.com/RAESystem/rae/commit/5a8b97a3a985f54de45337606ffdaae9dd3f5bd6))
* add governed scenario satisfiability analysis ([#842](https://github.com/RAESystem/rae/issues/842)) ([79b2854](https://github.com/RAESystem/rae/commit/79b2854e6c8bae982f8801319d9b46b60a5d9316))
* add network namespace sharing to SDL ([#853](https://github.com/RAESystem/rae/issues/853)) ([3f4911b](https://github.com/RAESystem/rae/commit/3f4911b94606580f9ce8193938963be10a85f89d))
* add portable trial cleanup contracts ([#854](https://github.com/RAESystem/rae/issues/854)) ([8040dbd](https://github.com/RAESystem/rae/commit/8040dbd354361ec106976f4ff2dc1a2a54104fb1))
* add processor plan CLI to serialize execution plans to JSON ([#830](https://github.com/RAESystem/rae/issues/830)) ([430aa8a](https://github.com/RAESystem/rae/commit/430aa8a76897ccaf0fb257f2c1706985a6131738))
* add researcher accessibility evidence protocol ([#821](https://github.com/RAESystem/rae/issues/821)) ([03a7856](https://github.com/RAESystem/rae/commit/03a7856eb3e3a30848639b5f9b6e981a52cc47b2))
* add typed exploit-path analysis ([#848](https://github.com/RAESystem/rae/issues/848)) ([42fc38a](https://github.com/RAESystem/rae/commit/42fc38aac0017853b7201042dd8b4efba9da3a9e))
* add validation profile catalog ([#867](https://github.com/RAESystem/rae/issues/867)) ([781b1ea](https://github.com/RAESystem/rae/commit/781b1ea1a6377d333558a883a0049de2910d3f6e))
* compile domain controller placements ([#858](https://github.com/RAESystem/rae/issues/858)) ([4ff18d1](https://github.com/RAESystem/rae/commit/4ff18d1500334746abbf72aecc467bafd7fa61d9))
* cut over public surfaces to RAES ([#870](https://github.com/RAESystem/rae/issues/870)) ([ecd6d79](https://github.com/RAESystem/rae/commit/ecd6d79dc6855f9d08e5d4b31d0ad9a4d12b2269))
* define participant decision surface semantics ([#844](https://github.com/RAESystem/rae/issues/844)) ([e60d839](https://github.com/RAESystem/rae/commit/e60d839f6d014a2bf3b18045770296812751dc21))
* define participant tool affordance semantics ([#838](https://github.com/RAESystem/rae/issues/838)) ([08909cf](https://github.com/RAESystem/rae/commit/08909cf232427971bd6a95023ac1d2e5d7936570))
* implement participant exposure semantics ([#852](https://github.com/RAESystem/rae/issues/852)) ([e499a4d](https://github.com/RAESystem/rae/commit/e499a4d9050fef581daaf5f9708fd0bf3fea7094))
* **runtime:** add trusted runtime fact bindings ([#846](https://github.com/RAESystem/rae/issues/846)) ([a6d2659](https://github.com/RAESystem/rae/commit/a6d2659f2c83da90de07376066652cc48e4adb74))
* **runtime:** execute benign participants under shared time ([#869](https://github.com/RAESystem/rae/issues/869)) ([07c8d50](https://github.com/RAESystem/rae/commit/07c8d5075d8f7a1a486ea4c55e898fb428dac7b4))
* **runtime:** publish portable shared time contracts ([#865](https://github.com/RAESystem/rae/issues/865)) ([2a76f39](https://github.com/RAESystem/rae/commit/2a76f39eca41b2776545b5d94d39e2b6dc69008e))
* **sdl:** add bounded scenario-family variation points ([#841](https://github.com/RAESystem/rae/issues/841)) ([ed56a44](https://github.com/RAESystem/rae/commit/ed56a44f24664f8844013d165f56ad9bf55d6195))
* **sdl:** add enterprise identity and deployment tenancy ([#860](https://github.com/RAESystem/rae/issues/860)) ([4b1f05a](https://github.com/RAESystem/rae/commit/4b1f05a15282c88352467e3e569990317cf01121))
* **sdl:** add initial service state materialization semantics ([#862](https://github.com/RAESystem/rae/issues/862)) ([80fbf14](https://github.com/RAESystem/rae/commit/80fbf146608b286a79c5996ec4f7ece8ea570d51))
* **sdl:** add mixed-control participant operations ([#840](https://github.com/RAESystem/rae/issues/840)) ([4a1061d](https://github.com/RAESystem/rae/commit/4a1061dee6a10ee5c0a95a3f4ab371d1553c2583))
* **sdl:** add shared time semantics and runtime control ([#864](https://github.com/RAESystem/rae/issues/864)) ([b13a178](https://github.com/RAESystem/rae/commit/b13a17887e17341bcceed62b7711a9f70a8a6635))
* **semantics:** define participant information-flow control ([#831](https://github.com/RAESystem/rae/issues/831)) ([fec6ea6](https://github.com/RAESystem/rae/commit/fec6ea686ef85afc776ddf084458c6cfa9949b9f))

## [0.23.1](https://github.com/Brad-Edwards/aces/compare/v0.23.0...v0.23.1) (2026-07-17)


### Bug Fixes

* enforce stateful resource admission ([#816](https://github.com/Brad-Edwards/aces/issues/816)) ([8bf12ee](https://github.com/Brad-Edwards/aces/commit/8bf12eeb0d43e6e23a86abb012d7b31b076bd69a))

## [0.23.0](https://github.com/Brad-Edwards/aces/compare/v0.22.0...v0.23.0) (2026-07-17)


### Features

* add DSL evaluation evidence gate ([#795](https://github.com/Brad-Edwards/aces/issues/795)) ([03c3101](https://github.com/Brad-Edwards/aces/commit/03c3101d48c359d96604d8227059af5c12c513e2))
* add stateful realization resources ([#782](https://github.com/Brad-Edwards/aces/issues/782)) ([5c47235](https://github.com/Brad-Edwards/aces/commit/5c472351c2d5ce15ca07fb03522f4a5846b6a63d))
* **sdl:** add participant interactive access ([#807](https://github.com/Brad-Edwards/aces/issues/807)) ([7e17b97](https://github.com/Brad-Edwards/aces/commit/7e17b97ce0e47ac11bfee278ccb872f6a57d2bf8))


### Documentation

* design deterministic scenario trial realization ([#804](https://github.com/Brad-Edwards/aces/issues/804)) ([60e9ad6](https://github.com/Brad-Edwards/aces/commit/60e9ad6b6d836b88283301f472f7a830e4edc51a))
* design participant information-flow control adoption ([#806](https://github.com/Brad-Edwards/aces/issues/806)) ([0c87adf](https://github.com/Brad-Edwards/aces/commit/0c87adf02105fe4269d9b77aacce8e86bdf968dc))

## [0.22.0](https://github.com/Brad-Edwards/aces/compare/v0.21.0...v0.22.0) (2026-07-15)


### Features

* add realization honesty conformance ([#777](https://github.com/Brad-Edwards/aces/issues/777)) ([5f4e3e7](https://github.com/Brad-Edwards/aces/commit/5f4e3e7ca78d21acc12a1ed563aa7f05b64b391a))
* **sdl:** add authored identity domain topology ([#768](https://github.com/Brad-Edwards/aces/issues/768)) ([78da8fd](https://github.com/Brad-Edwards/aces/commit/78da8fd2c970714232732767398f3b667cd832eb))


### Bug Fixes

* stop claiming unrealized domain support ([#778](https://github.com/Brad-Edwards/aces/issues/778)) ([38ba081](https://github.com/Brad-Edwards/aces/commit/38ba081714b12a4dcc7a5c527e2f1250d80a4d1b))


### Documentation

* define participant decision-surface semantics ([#774](https://github.com/Brad-Edwards/aces/issues/774)) ([1fd985b](https://github.com/Brad-Edwards/aces/commit/1fd985bb26ecc73b43189fc36584dfa72a80b941))
* **sdl:** align prose specification with live contracts ([#775](https://github.com/Brad-Edwards/aces/issues/775)) ([4667c90](https://github.com/Brad-Edwards/aces/commit/4667c901c404860e2bda334557bd452ef27cd1c9))

## [0.21.0](https://github.com/Brad-Edwards/aces/compare/v0.20.0...v0.21.0) (2026-07-14)


### Features

* add scoped realization posture cascade ([#766](https://github.com/Brad-Edwards/aces/issues/766)) ([7776866](https://github.com/Brad-Edwards/aces/commit/77768667242a23728a96aeed9294f62fca30831a))
* define behavioral relation taxonomy and claim discipline ([#770](https://github.com/Brad-Edwards/aces/issues/770)) ([feed07d](https://github.com/Brad-Edwards/aces/commit/feed07d303dbcbbb9bf4230a72ea5ca9c49f279f))


### Bug Fixes

* define node service reachability semantics ([#764](https://github.com/Brad-Edwards/aces/issues/764)) ([2c3fa06](https://github.com/Brad-Edwards/aces/commit/2c3fa06a40f69095191b029fcb1062ebfe3b5f60))
* preserve explicitness provenance at runtime ([#762](https://github.com/Brad-Edwards/aces/issues/762)) ([1b63b2a](https://github.com/Brad-Edwards/aces/commit/1b63b2a0b10dcd80e29b8bad14558ad9c6b706d0))
* **sdl:** separate runtime contract from observed evidence ([#761](https://github.com/Brad-Edwards/aces/issues/761)) ([69acb69](https://github.com/Brad-Edwards/aces/commit/69acb691435c72f4a831358d7ee2f83ab3fcf663))


### Documentation

* rebuild related-work comparison from reproducible evidence ([#765](https://github.com/Brad-Edwards/aces/issues/765)) ([ed9577a](https://github.com/Brad-Edwards/aces/commit/ed9577aecbe65de19953a45744d3bdc219d9af0b))

## [0.20.0](https://github.com/Brad-Edwards/aces/compare/v0.19.1...v0.20.0) (2026-07-13)


### Features

* add experiment authoring-input contract and MCP authoring surface ([#711](https://github.com/Brad-Edwards/aces/issues/711)) ([ac5f697](https://github.com/Brad-Edwards/aces/commit/ac5f69719c87f7fb4fa85aa2c3a141c834a6ec73))
* define associated artifact manifest contracts ([#741](https://github.com/Brad-Edwards/aces/issues/741)) ([066b3f0](https://github.com/Brad-Edwards/aces/commit/066b3f0c6103deb732795ebba90c4822d798f942))
* define backend-neutral proposition semantics ([#744](https://github.com/Brad-Edwards/aces/issues/744)) ([ccb4913](https://github.com/Brad-Edwards/aces/commit/ccb49134395ff51120710981e209d97b791129c5))
* enforce closed SDL phase contracts ([#742](https://github.com/Brad-Edwards/aces/issues/742)) ([b2f0756](https://github.com/Brad-Edwards/aces/commit/b2f0756440aa18b43e33ca685ee0a666f64b10aa))
* enforce portable SDL identifiers ([#736](https://github.com/Brad-Edwards/aces/issues/736)) ([40af65b](https://github.com/Brad-Edwards/aces/commit/40af65b9513023a380b8121ad412686a9e08dc8c))
* enforce TechVault realization disclosure ([#735](https://github.com/Brad-Edwards/aces/issues/735)) ([47e7220](https://github.com/Brad-Edwards/aces/commit/47e72201cd3b36b6b1c45467add2246a0b4186b4))
* expose completeness profiles through MCP ([#755](https://github.com/Brad-Edwards/aces/issues/755)) ([23021cf](https://github.com/Brad-Edwards/aces/commit/23021cf027e787bf66303539a652905c701e1075))
* **libvirt:** add guest-observed realization probes (ASR-519) ([#737](https://github.com/Brad-Edwards/aces/issues/737)) ([ef4cbed](https://github.com/Brad-Edwards/aces/commit/ef4cbed0a5eabb2e873e90bae2f05a049a39b9f9))
* **libvirt:** publish configuration-bound realization envelopes ([#730](https://github.com/Brad-Edwards/aces/issues/730)) ([7d48c05](https://github.com/Brad-Edwards/aces/commit/7d48c0531db294c18826382dec0ef6209197495c))
* publish revision-pinned SDL lineage ledger ([#745](https://github.com/Brad-Edwards/aces/issues/745)) ([04ccd2f](https://github.com/Brad-Edwards/aces/commit/04ccd2f5bdd8e5ab53730942defcd6e63bca74c8))
* publish scientific scenario completeness profiles ([#751](https://github.com/Brad-Edwards/aces/issues/751)) ([d2774d9](https://github.com/Brad-Edwards/aces/commit/d2774d980a376553e34a5e7032199232d37f32b4))
* **sdl:** add DSL-115 authoring specificity helper ([#710](https://github.com/Brad-Edwards/aces/issues/710)) ([a6036f4](https://github.com/Brad-Edwards/aces/commit/a6036f4cb0049c42217f28304070fc3b197d35b9))
* **sdl:** add realization-envelope membership/subsumption/witness relation ([#668](https://github.com/Brad-Edwards/aces/issues/668)) ([#685](https://github.com/Brad-Edwards/aces/issues/685)) ([24d3e09](https://github.com/Brad-Edwards/aces/commit/24d3e097bae4d4e90032ab985f12702c8ad798f9))
* **sdl:** define canonical YAML source profile ([#732](https://github.com/Brad-Edwards/aces/issues/732)) ([04d0682](https://github.com/Brad-Edwards/aces/commit/04d068208381410cc56468c9db2dcff92b2aa263))


### Bug Fixes

* derive honest version identifiers, consolidate on release-please (GOV-901) ([#750](https://github.com/Brad-Edwards/aces/issues/750)) ([526e777](https://github.com/Brad-Edwards/aces/commit/526e7770f178798db6ea5691f7770ba62d998b0f))
* reject ambiguous SDL mapping keys ([#731](https://github.com/Brad-Edwards/aces/issues/731)) ([2a70e6a](https://github.com/Brad-Edwards/aces/commit/2a70e6ae92d96f3e7542d3f930ac6fb240244102))


### Documentation

* define ecosystem evolution governance policy ([#718](https://github.com/Brad-Edwards/aces/issues/718)) ([73d1a0f](https://github.com/Brad-Edwards/aces/commit/73d1a0ffd6f487ffc1d5dcfa63366bd069997482))

## [0.19.1](https://github.com/Brad-Edwards/aces/compare/v0.19.0...v0.19.1) (2026-07-06)


### Bug Fixes

* publish the project README as the PyPI description ([#701](https://github.com/Brad-Edwards/aces/issues/701)) ([6a56f93](https://github.com/Brad-Edwards/aces/commit/6a56f93d35e50a2362c13a81700f332f8a2709ca))

## [0.19.0](https://github.com/Brad-Edwards/aces/compare/v0.18.0...v0.19.0) (2026-07-06)


### Features

* add ADR amendment policy and acceptance-content pin gate (GOV-941) ([8c58ab5](https://github.com/Brad-Edwards/aces/commit/8c58ab5d34129da32573845ff5a31d7569d20b00))
* add authored evidence requirements ([b41584b](https://github.com/Brad-Edwards/aces/commit/b41584be704c3dea9062e10cdfe99275c8462cdf))
* add behavior specifications to SDL ([039b019](https://github.com/Brad-Edwards/aces/commit/039b0197b896803fa4c4d70a49eaf650080148af))
* add dns runtime inventory ([2f61056](https://github.com/Brad-Edwards/aces/commit/2f6105631e69444467d2aaa9dfd5aef0e4a47cb8))
* add explicitness classifier semantics ([26a22da](https://github.com/Brad-Edwards/aces/commit/26a22da9c7ce9eaff571296ac1578f36c07adf11))
* add libvirt participant runtime for the paper scenario ([554a139](https://github.com/Brad-Edwards/aces/commit/554a139fb62b4873ffea8141051520ef800df2cc))
* add libvirt provisioning backend ([7da3293](https://github.com/Brad-Edwards/aces/commit/7da329364620a31f543fec77c8b2fdf62130d8dd))
* add operational apparatus summary ([b26876c](https://github.com/Brad-Edwards/aces/commit/b26876c401667ec5ba96b4de5d72521a55989fa8))
* add participant concurrency runtime contracts ([9827df8](https://github.com/Brad-Edwards/aces/commit/9827df8aad84c94c8d8f53825672e8a651adb421))
* add repository-owned reference processor (RUN-313) ([106122b](https://github.com/Brad-Edwards/aces/commit/106122b7589f673ca57fa1d9bd35f51c65c23161))
* add scenario-level forwarding agents ([a7467df](https://github.com/Brad-Edwards/aces/commit/a7467df3b2366c8d4d6f5f044ab7623c27830081))
* add scenario-native observability coverage ([3e9f5db](https://github.com/Brad-Edwards/aces/commit/3e9f5dbbf65c70ad4ac88da8e6f852629c3fb4e4))
* bind participant implementations to runtime actions ([d28d314](https://github.com/Brad-Edwards/aces/commit/d28d3140d78b9ce1115ed3e946f5eb81e0c0c3c4))
* **corpus:** add paper demonstration corpus with cross-backend invariant ledger ([ce1bc07](https://github.com/Brad-Edwards/aces/commit/ce1bc07ab8bb80e7afaf6c304ac69f4a2e5dd8ec))
* define SEM-216 boundary semantics for state, evidence, evaluation, analysis, and views ([2c72e7f](https://github.com/Brad-Edwards/aces/commit/2c72e7f600f7a20f205b45754747934c4f6de438))
* **DSL-132,DSL-133:** add datastore_services and platform_applications spines ([aaef653](https://github.com/Brad-Edwards/aces/commit/aaef6530d56ae02e929ec98c275139b82a0ebf04))
* **DSL-134,DSL-135:** add app_authorization and scheduled_jobs runtime families ([4d02197](https://github.com/Brad-Edwards/aces/commit/4d02197de616cc58fc50af44400b85551db79c7a))
* **DSL-136,DSL-137:** add forwarding_agents and orchestration_authorities families ([b9f9f12](https://github.com/Brad-Edwards/aces/commit/b9f9f123318e8afe461195d0b11392871deb7dc1))
* **DSL-138:** add typed runtime relationship subtypes + route upstream_target ([4e0f631](https://github.com/Brad-Edwards/aces/commit/4e0f631af89676c0212dcaa2d711c54bb27e04e7))
* emit SEM-218 realization requirements and gate the planner on backend support ([38f925f](https://github.com/Brad-Edwards/aces/commit/38f925f2dde5cab96320139de7199e956d475321))
* implement SEM-224 observability plane separation semantics ([eba8724](https://github.com/Brad-Edwards/aces/commit/eba87241b4c02bbc4b5a5c86f9b71010bccafa04))
* **libvirt:** typed capability diagnostics for out-of-envelope plan terms ([7b298e9](https://github.com/Brad-Edwards/aces/commit/7b298e90e7a79a50bae34b42a2d2d0c318a29756))
* **libvirt:** typed capability diagnostics for out-of-envelope plan terms ([1db2597](https://github.com/Brad-Edwards/aces/commit/1db2597c09494664aa656ab0a4be307b1ae9ca76))
* realize plan resources on libvirt (domains, networks, placements) ([72b87e0](https://github.com/Brad-Edwards/aces/commit/72b87e07f2ac04fbd144110f0c3d13b9793fd7e9))
* register API-406 backend carrier contracts ([59cfd43](https://github.com/Brad-Edwards/aces/commit/59cfd43a4275f4e41234f901a85895f522966c69))
* **runtime:** add shared operational state snapshots ([29ca38c](https://github.com/Brad-Edwards/aces/commit/29ca38c70081b25b430717ea9984752c6987f848))
* **runtime:** add shared operational state snapshots ([5ca2c2b](https://github.com/Brad-Edwards/aces/commit/5ca2c2b969812a0c38bc283a7f4d506591c99047))
* ship contract corpus as package data and add a versioned release line ([8c0ddd8](https://github.com/Brad-Edwards/aces/commit/8c0ddd89809ac6332ff318fa7fd73c93ed46d209))


### Bug Fixes

* backfill schema-publication ledger entries to unblock dev-&gt;main ([27c2fb0](https://github.com/Brad-Edwards/aces/commit/27c2fb0c0b13d237f2d058b2afef62883bb4dedf))
* clear SonarCloud new-code findings in the libvirt backend ([180715a](https://github.com/Brad-Edwards/aces/commit/180715a855c4e6c12c7fb5819d997db5a5050671))
* consolidate runtime validation helpers ([bfab7e1](https://github.com/Brad-Edwards/aces/commit/bfab7e1e0709eda2b00318fc36564257a8de034a))
* consolidate runtime validation helpers ([6958fed](https://github.com/Brad-Edwards/aces/commit/6958fed460067cd5a3b9c5dd6a4a2ca6cfd75aae))
* **DSL-132:** tighten SCN-010 SDL validation closure ([d727d84](https://github.com/Brad-Edwards/aces/commit/d727d84a2b6f0365211cba6310044446e889cd98))
* honor reconciliation and make libvirt backend teardown idempotent ([a2ccc81](https://github.com/Brad-Edwards/aces/commit/a2ccc8158b797f2181fc73bda5d85f7dc5429902))
* preserve inventory target secrets ([26e5abb](https://github.com/Brad-Edwards/aces/commit/26e5abb2c80bdd10df1f4e2a4b7978380c633102))
* **runtime:** clear shared-state sonar findings ([4d464c4](https://github.com/Brad-Edwards/aces/commit/4d464c466066e7eb8b579cb7577faee312c8e0dc))
* **runtime:** simplify shared-state validators ([c19f282](https://github.com/Brad-Edwards/aces/commit/c19f282ff737a4c9b1292269e819c102a949cc45))
* **sdl:** make local import lockfile resolved_source checkout-independent ([15b7121](https://github.com/Brad-Edwards/aces/commit/15b7121c7e6257b564e1c36ce0a9b723441c3899))
* unify runtime service family registry ([ffe28e5](https://github.com/Brad-Edwards/aces/commit/ffe28e596840cc37d152f63880a889a7477a5911))


### Documentation

* accept participant ADR dependency chain ([cee0543](https://github.com/Brad-Edwards/aces/commit/cee05438a6c49295d5cfb7df81c7138817603f2c))
* add CAGE-2 replication architecture ([7ad0276](https://github.com/Brad-Edwards/aces/commit/7ad0276003d88fc3673f3f4768d857580c124f16))
* add participant runtime design ([bb087e9](https://github.com/Brad-Edwards/aces/commit/bb087e99dfb5d773e7a6f30f7d4db6c372ae5b85))
* add proposed ADR-073 on scoring/reward language scope ([c8bbbad](https://github.com/Brad-Edwards/aces/commit/c8bbbad68c2d4bd8938918d9a70f98c7d62fe292))
* add related-work comparison positioning ACES against precedent systems ([0fe9f1f](https://github.com/Brad-Edwards/aces/commit/0fe9f1fc39dce1ec8ec1c9478d96f7eb7ea49561))
* add SDL module composition ADR ([22bbbdb](https://github.com/Brad-Edwards/aces/commit/22bbbdb5f76d4a5b09385ce428b7e420e209f899))
* add validation admission profile design ([4df4e8e](https://github.com/Brad-Edwards/aces/commit/4df4e8e5c066bbbc1d2612b066fe1a8aff0393b1))
* author the SDL prose specification under specs/sdl/ (CT-6) ([792c207](https://github.com/Brad-Edwards/aces/commit/792c207950211f25166139e7035a3509570b6f49))
* define experiment replication and replay claims ([bed09cf](https://github.com/Brad-Edwards/aces/commit/bed09cf75b17bf52b19c8cdbcfaab3bd6db7bfb1))
* document ACT-603 interaction guardrails ([0be0e79](https://github.com/Brad-Edwards/aces/commit/0be0e79c957a490e945cbe9fca09186d1a39140d))
* document observability evidence plane separation ([9fd2b73](https://github.com/Brad-Edwards/aces/commit/9fd2b73f9a578b8270ac3921ca21cd87720fd7a9))
* document realization envelope semantics ([bfe4515](https://github.com/Brad-Edwards/aces/commit/bfe4515b27ce6cf3bc09283be0c4a8e70f36a597))
* **DSL-139:** backfill limitations.md family coverage + confirmation-folds doctrine ([eb49821](https://github.com/Brad-Edwards/aces/commit/eb49821b2546f56c9f8cd512ccd969624d1b55d5))
* **experiment-core:** define replication and replay claims ([09d56df](https://github.com/Brad-Edwards/aces/commit/09d56dff861087cc74f87c46b49e3b25565faeeb))
* reconcile asset inventory methodology closeout ([4a1fddb](https://github.com/Brad-Edwards/aces/commit/4a1fddbbbcaa0f3718f26363c3d011eaf8b97bba))
* reconcile asset inventory methodology closeout ([ba18151](https://github.com/Brad-Edwards/aces/commit/ba18151b2a665bcc85eb4417915297ec7c6464f7))
* record api-419 preflight guardrails ([b61eb02](https://github.com/Brad-Edwards/aces/commit/b61eb024a37be7114d3c5cce645ae9ce3c7ef1fb))
* register gap remediation overlay ([ee74846](https://github.com/Brad-Edwards/aces/commit/ee74846a4210e3299f981b6c6bc54429b3ebf2b5))
* **scn010:** add expressivity gap analysis and wire toctree ([0cdc927](https://github.com/Brad-Edwards/aces/commit/0cdc92791c40cd14c4bc3cdb97259f7fbf013ca6))
* **security:** record 2026-07-01 commit authorship anomaly ([5eb8078](https://github.com/Brad-Edwards/aces/commit/5eb8078047a17890e819d8d5867c59acc79c8320))
* **security:** record 2026-07-01 commit authorship anomaly ([b648c99](https://github.com/Brad-Edwards/aces/commit/b648c99e8716b634fa2b48ec3f0902734d0bd585))
* tighten citation hygiene across SDL lineage and precedent docs ([0059d03](https://github.com/Brad-Edwards/aces/commit/0059d03af5c6280655eb41c07b8a094388b9f4e2))

## [0.18.0] - 2026-07-06

### Security

- Bound OCI module import fetches against memory and disk exhaustion. The registry resolver now caps every remote response before buffering it — a separate, larger limit for the compressed bundle blob than for tag-list, manifest, and config metadata — rejecting an oversized or invalid `Content-Length` early and enforcing the cap on the bytes actually read so a compromised or malicious registry cannot force an unbounded in-memory buffer. Bundle extraction additionally bounds the tar member count, per-member extracted size, and total extracted bytes (rejecting duplicate paths), iterating members lazily so an oversized or decompression-bomb bundle fails closed before the archive is fully unpacked. Explicit network timeouts and the issue #13 tar path/link/mode safety checks remain in force. (#12)- Harden OCI module bundle extraction to fail closed on every supported Python runtime. The resolver now validates the entire tar archive before writing — rejecting path traversal, symlinks, hard links, and special files, and stripping setuid/setgid/sticky bits — instead of relying on `tarfile`'s `filter="data"`, which is unavailable on Python 3.11.0–3.11.3 (the PEP 706 backport landed in 3.11.4) and previously allowed an unsafe extraction path on those supported runtimes. (#13)- Bind the OCI module config object into the resolver's trust boundary. The registry resolver now verifies that the fetched config blob bytes hash to the manifest's `config.digest` before decoding it — fetching by digest is not integrity, so a compromised registry could previously serve arbitrary config bytes (carrying the unsigned `root_file` entrypoint) under a valid manifest. The Ed25519 signature payload now also binds `root_file` alongside the module identity, exports, and bundle `content_digest`, and the resolver verifies the signature over the same `root_file` it extracts. Together these close a semantic-substitution attack where a registry that cannot alter the signed bundle could still repoint resolution to a different file already inside that bundle by rewriting `root_file`. Signatures produced over the previous payload (which omitted `root_file`) fail closed when signatures are required. (#14)- Port runtime control-plane and SDL module-registry security hardening onto the current package layout. (#143)- Protected branches (`main`, `dev`) now enforce the CI-strictness baseline: all
  CI checks are required and strict, the SonarCloud quality gate is waited on and
  fails on any new issue, and pre-commit file hygiene plus secret scanning run in
  CI — so nothing merges past a failing check or a failing quality gate, while
  admin override is retained. (#527)- Bumped `asyncssh` (2.23.1), `cryptography` (49.0.0), `idna` (3.18), `pytest` (9.1.0), and `starlette` (1.3.1) in the Python lockfile to clear five moderate Dependabot advisories: AsyncSSH `AuthorizedKeysFile %u` path traversal (GHSA-g794-3fmp-753h), cryptography non-contiguous-buffer overflow (GHSA-p423-j2cm-9vmq), idna `encode()` CVE-2024-3651 bypass (GHSA-65pc-fj4g-8rjx), pytest tmpdir handling (GHSA-6w46-j5rx-g56g), and Starlette missing Host-header validation (GHSA-86qp-5c8j-p5mr). The directly-declared floors for `cryptography`, `asyncssh`, and `pytest` were raised to their patched versions to prevent regression.

### Added

- Added an advisory (non-gating) OSV-scanner CI job that scans `implementations/python/uv.lock` for known CVEs against the OSV.dev advisory feed and publishes the findings as a JSON report artifact. (#34)- Canonical machine-readable mapping for the classification-based assurance policy (ASR-505): `specs/formal/assurance-policy.yaml` enumerates every `FM` level's required and prohibited artifacts; `tools/check_assurance_policy.py` gates drift in CI; ADR-018 records the decision and `docs/specs/formal.md` is realigned to ADR-007's level names. (#68)- Add the canonical normative-artifact authority-boundary manifest for ASR-517 (`specs/authority/authority-boundary.yaml`), governed by ADR-019, with a structural gate (`tools/check_authority_boundary.py`) wired into `nox -s policy`. (#69)- Add declarative participant framing fields to the SDL `agents` section (ACT-601, ADR-020): `starting_conditions`, `authority_anchors`, and `operating_scope` on `Agent`, with semantic validation against the `conditions` section and the named-reference / targetable indexes. Identity and role continue to come from `Agent.entity` and `Entity.role`. (#70)- Added the issue 71 participant-semantics design ADR, formal spec, and lineage
  documentation for SEM-208, SEM-209, SEM-210, SEM-211, SEM-212, SEM-213, and
  SEM-215.

  Recorded cross-issue design deferrals for benchmark anti-contamination,
  machine-checkable participant conformance, and DSL language adequacy evidence,
  including GitHub issue #346 for DSL evaluation/language adequacy. (#71)- Added the normative SEM-218 explicitness and realization semantics spec at
  `specs/formal/realization/explicitness-and-realization.md`, distinguishing
  binding author declarations from open backend realization and stating the
  fail-closed rule for unsupported exact requirements. The spec scopes
  realization-support disclosure to backend manifests only (processor
  manifests carry no `realization_support` because the processor layer
  does not realize underspecified concerns), and records its current
  realization status as `partial` in the SEM-200 coverage table.
  Enforcement today is the narrow structural floor: the apparatus-contract
  shape gates on backend `RealizationSupportDeclaration`, the JSON-schema
  conditional gate, the processor-manifest asymmetric rejection of
  `realization_support`, and the closed-Pydantic SDL model boundary. The
  SEM-218 classifier (exact / constrained / open) in `SemanticValidator`,
  the typed compiler emission, the planner-side match against backend
  `realization_support`, the runtime non-approximation envelope, and the
  SEM-218 provenance fields are normative for the implementation work
  that lifts the row from `partial` to `active`. (#72)- Added the issue 74 participant-runtime design ADR and formal spec for RUN-305,
  RUN-306, RUN-307, and RUN-308, including explicit support for opaque LLM, RL,
  human, script, and external-service participants whose internal decision loops
  are not exposed to ACES. (#74)- ### Added

  - Published the joint participant backend-facing contract surface (ADR-060;
    API-405/406/407/408/411 design issue #76): a `participant-runtime` schema
    family (`participant-lifecycle-event-v1`,
    `participant-observation-envelope-v1`,
    `participant-shared-state-record-v1`, `participant-outcome-report-v1`),
    control-plane retrieval projections (`participant-status-view-v1`,
    `participant-history-view-v1`, `participant-context-view-v1`), an API-407
    `feature_support` extension of the backend-manifest
    `capabilities.participant_runtime` block on the ADR-054 guarantee-strength
    scale (with the `participant-runtime-feature-support-levels` controlled
    vocabulary), the normative spec section
    `specs/formal/runtime-contracts/participant-backend-contracts.md`, and the
    research notes under `docs/research/participant-backend-contracts/`.
    Design-issue scope only: shapes, schemas, and fixtures; runtime emission
    and conformance land on #200-#203. (#76)- Added the participant behavior model ADR and formal spec covering ACT-602,
  ACT-603, ACT-606, ACT-607, and ACT-608. (#77)- Added the experiment-core task, run, apparatus-context, and study/collection
  contract design with generated schema support and published schema
  descriptions. The contracts include semantic validators for task/run apparatus
  constraints, manifest payload binding, study metric grounding, semantic-
  invariant annotation shape checks, required wire-level schema versions,
  study metric result coverage, study run-allocation coverage, and RFC 3339
  case/valid-leap-second validation. Run-allocation coverage now requires
  explicit condition assignments to declared study factors, declared blocking
  factors with operational levels and appropriate factor kinds, distinct
  factor-level combinations, distinct auditable non-opaque run-level criteria,
  and exactly-one condition satisfaction for included runs. It also excludes
  invalidated, superseded, and not-evaluated runs from analysis allocation and
  from analysis-bearing collection/cohort records. The final traceability pass
  adds a literature/lineage criteria matrix, binds digest/path-bearing task and
  metric evidence requirements to concrete run artifact checksum and URI/path,
  prevents redacted or withheld experiment parameters from carrying concrete
  values, requires validity notes for claim-bearing study and benchmark records,
  and exposes explicit benchmark/agent-evaluation artifact roles for starter
  files, evaluators, subtasks, gold steps, milestones, human assistance,
  scaffolds, baselines, and cost/resource traces. Digest-bound semantic
  validation treats schema-valid hex case variants as the same digest, optional
  reference qualifiers constrain only when supplied, and unsupported
  identity-reference digest/path qualifiers cannot silently satisfy apparatus or
  run-allocation criteria. Schema semantic-invariant annotations must resolve to
  callable validators, and declared run allocations are checked even when a
  collection/cohort omits an analysis plan.
  Experiment artifact references now require explicit sensitivity metadata, and
  EXP-701 through EXP-705 are mapped to the generated schema publication surface
  in requirement governance. Task records require leakage, apparatus, validity,
  and supporting-artifact disclosure surfaces, and run-allocation condition
  assignments now reject empty criteria at the JSON Schema boundary. Identity
  references for processor/backend apparatus constraints reject digest/path
  qualifiers. Generic scenario refs, run task refs, study task/run membership
  refs, run-internal result evidence refs, artifact `satisfies_refs`, and all
  run-allocation condition refs now also reject qualifiers they cannot bind.
  Apparatus manifest validation rejects ambiguous selected-manifest subject
  bindings, manifest path qualifiers, unvalidated digest-qualified manifest refs,
  digest-qualified selected manifests that are not canonical component manifests,
  processor/backend required manifest ids that do not match subject identities,
  and mutually incompatible processor/backend manifest payloads. Apparatus
  compatibility refs and measurement-channel refs now reject digest/path
  qualifiers, including explicit null fields, so candidate run metadata cannot
  satisfy id-only task or study criteria while carrying unvalidated checksum/path
  claims.
  Experiment core now incorporates participant implementation manifest and
  provenance contracts, requires participant implementation apparatus to bind to
  participant manifests and run-level provenance, resolves participant study
  criteria through selected run provenance, renumbers the experiment ADR to avoid
  the current SDL ADR range, and documents scenario-snapshot identity over
  expanded canonical SDL module compositions. (#87)- Add the experiment evidence and measure contract boundary for EXP-707, EXP-708, EXP-709, and EXP-715. The experiment-core schema family now publishes `experiment-capture-spec-v1`, `experiment-evidence-record-v1`, and `experiment-derived-measure-v1`, with valid/invalid fixtures, semantic invariant annotations, and conformance validators that keep declarative capture intent, raw evidence, and derived measures separate. Backend manifests now support an optional `capabilities.observation` block with governed capture-kind, channel-kind, and sealing-mode vocabularies, and conformance rejects observation claims that lack the published evidence contracts. ADR-064 and the formal experiment-core spec record the boundary; runtime capture, storage, APIs, schedulers, and statistical engines remain out of scope for this contract-only change.
  Refactor the reported-value invariant helper and observation capability gap reporting so SonarCloud quality gates remain clean for the published contract surface. (#88)- Extend `experiment-run-v1` as the canonical run provenance record for EXP-710, EXP-720, and EXP-722. Run records now include required traceability links from capture specs to raw evidence, derived measures, and claims, plus realized-form disclosures for processor/backend/operator choices that were not fully authored in the scenario or task. ADR-065 and the formal experiment-core spec document the boundary; generated schemas, fixtures, and contract tests enforce the new provenance surface. Reference de-duplication now also tolerates constrained experiment reference models that omit optional digest, path, or subject fields. (#89)- ### Added

  - Added the ASR-511/ASR-515 validation and admission profile design, including
    ADR-072, the formal validation-basis disclosure spec, and the clause matrix. (#97)- Add EXP-706/EXP-712 trial, replication, reproducibility, and replay-claim
  design guidance for experiment-core ADRs, formal specs, and preflight
  guardrails. (#105)- Publish the GOV-913 reusable-asset trust, authenticity, and integrity policy:
  a normative spec (`specs/supply-chain/reusable-asset-trust-integrity.md`),
  ADR-071, and the `reusable-asset-trust-policy-v1` contract declaring, per
  reusable asset family, the required integrity/authenticity/provenance/governance
  evidence classes referencing existing ACES trust mechanisms. (#115)- Added participant implementation manifest and provenance contracts with generated schemas, fixtures, conformance validation, and documentation. (#129)- Added the proposed falsification-first claim evidence gate ADR for ASR-530. (#162)- Added governed participant behavior contracts, observation boundaries, compiled participant behavior addresses, and a published participant behavior history stream for SEM-208. (#185)- Add explicit SEM-209 participant interaction semantics for action contracts, behavior history provenance, reference validation, and joint-action ordering conformance. (#186)- Add SEM-210 participant visibility and information-boundary contracts with ordered, evidence-backed view transitions, runtime view-relation timelines, behavior-history anchors, snapshot-scoped hidden-truth observation guards, closed participant observation detail metadata, and fail-closed reference validation. (#187)- ### Added

  - Added typed participant action precondition, effect, failure, and action-result semantics for SEM-211,
    including complete precondition coverage checks, declared reference validation, action-result
    evidence grounding, observation-boundary authorization, action-result observation-point anchoring, and durable
    participant behavior-history persistence. (#188)- ### Added
  - Add SEM-212 participant attribution edge semantics, runtime validation, contract schema publication, and adversarial tests.
  - Refactor participant attribution event parsing and validation helpers for the SonarCloud complexity gate. (#189)- ### Added

  - Added SEM-213 temporal participant contracts, runtime temporal-context
    validation, backend timing disclosures, generated schema publication, and
    adversarial tests for domain/clock/disclosure, contract-shape, bounded timing,
    and cadence/deadline/dwell/timeout state-machine failures. (#190)- Add explicit SEM-215 participant outcome interpretation rules and runtime records that relate participant-local outcomes to objective, workflow, evaluation, evidence, and reward meaning only through declared provenance-bearing rules. (#191)- Added RUN-305 participant runtime state/history enforcement: behavior history now
  survives public runtime snapshots, uses tighter generated schema constraints,
  and is rejected on backend apply when the snapshot shape, participant identity,
  episode anchoring, append-only history prefix, or metadata boundary is invalid.
  The behavior-history model now also rejects boolean `realized_order` values so
  Python model validation matches the published JSON Schema and semantic validator. (#192)- Added RUN-306 participant runtime lifecycle fields and Sonar-clean shared validation to behavior-history event contracts, schemas, and validators. (#193)- ### Added
  - Added first-class RUN-307 shared operational state records/history to runtime snapshots with revision-aware validation.
  - Added semantic diagnostics for malformed shared-state records, access markers, and append-only history violations. (#194)- Added RUN-308 participant-runtime contract surfaces for joint action records, time-management contexts, runtime snapshot concurrency validation, and coverage for the concurrency guardrails. (#195)- Add a repository-owned reference processor (`aces_processor.reference.run_reference_processor` / `ReferenceProcessor`) that realizes the normative processing model: it carries SDL authoring input through instantiation, compilation, and planning to a portable execution plan and exposes the published processor manifest. Per ADR-008 the processor stops at the execution plan; backend realization stays in the runtime. The backend-conformance live probe now consumes the reference processor instead of inlining the compile/plan chain, and new tests drive its plan through the reference runtime to prove every contract version the processor manifest declares is exercised end to end. (RUN-313) (#196)- Add a repository-owned reference emulation backend (`aces_reference_backend`) that implements the four backend protocol roles (Provisioner, Orchestrator, Evaluator, ParticipantRuntime) over a pluggable deployment driver. The default in-process driver is hermetic; an opt-in OCI driver realizes plans against a real container runtime (docker/podman) through fixed-argv subprocess calls with bounded timeouts and no secret/native-id leakage into any portable artifact. The backend publishes identity/capability through the standard `BackendManifest`, registers on the existing `BackendRegistry` descriptor seam as `reference-emulation`, and passes `run_target_conformance` at the `FULL_REMOTE_CONTROL_PLANE` profile. Provenance flows through the SEM-218 apply gate; only portable ACES facts reach snapshots, diagnostics, and conformance reports. A `docker`-marked, runtime-gated integration test and a non-blocking `integration_docker` nox session / CI job exercise real-container realization without touching the hermetic `verify` graph. (RUN-314, ADR-063) (#197)- Backend manifests now declare supported participant roles, behavior features, and interaction features on participant runtime capability blocks. (#199)- ### Added

  - Made the API-406 participant lifecycle-event, observation-envelope, and
    shared-state record contracts required by the full remote control-plane
    backend profile and registered their conformance model validators. (#200)- Expose API-407 participant feature-support declarations through backend manifest capability helpers and preserve them in rendered backend-manifest v2 payloads. (#201)- Expose API-408 participant status, history, and reference/provenance context retrieval views through the runtime control plane and HTTP API. (#202)- Expose ACT-607 participant authority and scope declarations as compiled runtime metadata. (#207)- Added ACT-608 participant behavior-mode scope validation so authored behavior specifications resolve through the governed decision-surface mode vocabulary. (#208)- Added ACT-609 offensive behavior refs on behavior specifications, backed by separately governed MITRE ATT&CK Enterprise tactics v19.1 and MITRE ATLAS tactics v2026.06 vocabularies, pinned source lineage, SDL validation, generated schemas, and compiler carry-through. (#209)- Added claim-aware ACES MCP tools for parsing, compile/plan dry runs, manifest introspection, design assessment, and supported-claim assessment for scenario authors. (#223)- Added SDL language-service helpers and MCP tools for completions, references, formatting, structured diagnostics, and structured edits.
  Refined reference navigation and structured edit coverage for SonarCloud quality gates.
  Consolidated language-service diagnostic payload helpers to avoid duplicated implementation blocks. (#224)- Add a canonical AUT-811 agent guidance profile, checker, MCP tool, tests, and docs for machine-readable scope boundaries, invariants, review priorities, and safe-operating expectations. (#225)- Added a repo-wide documentation style guide, glossary, reference map, documentation-scope guidance, and corrected setup references for current-state, cited technical and academic prose; local nox pre-commit hooks now run serially to avoid concurrent schema-generation races during all-files checks. (#226)- Added current-state getting-started guidance and an examples inventory that state available ACES entrypoints, validation levels, and unsupported template or pattern surfaces. (#227)- Add negative conformance coverage and an invalid fixture for the EXP-707 experiment-capture-spec-v1 contract: a dedicated rejection test exercising the capture-requirement key-equality, window-reference resolution, capture-window time-ordering, and under-specified-window invariants, plus a schema-and-model invalid fixture for a window that declares no start, end, or trigger. (#233)- Add negative conformance coverage and invalid fixtures for the EXP-708 experiment-evidence-record-v1 contract: a dedicated rejection test exercising the content-uri-requires-checksum, non-empty source-refs, RFC 3339 captured-at, and redaction-requires-loss-disclosure invariants, plus schema-and-model invalid fixtures for a content URI without a checksum, an empty source-refs list, and a malformed captured-at timestamp. The model and published schema shipped under #88; this change adds the conformance tests of record without changing them. (#234)- Add negative conformance coverage and invalid fixtures for the EXP-709 experiment-derived-measure-v1 contract: a dedicated rejection test exercising the reported-requires-value, non-reported-must-not-carry-value, and RFC 3339 generated-at invariants, plus schema-and-model invalid fixtures for a reported measure without a value, a withheld measure carrying a value, and a malformed generated-at timestamp. The model and published schema shipped under #88; this change adds the conformance tests of record without changing them. (#235)- Add negative conformance coverage and invalid fixtures for the EXP-720 experiment-run-v1 canonical run provenance contract: a dedicated rejection test exercising the run-traceability claim-grounding and duplicate-reference invariants, the realized-form-disclosure substantive and processor/backend authority invariants, and the required traceability capture-spec surface, plus schema-and-model invalid fixtures for a realized-form disclosure missing a realized target, a backend-realized disclosure carrying a processor realization authority, and a run whose traceability omits capture-spec references. The model and published schema shipped under #89; this change adds the conformance tests of record without changing them. (#238)- Add negative conformance coverage and an invalid fixture for the EXP-722 experiment-run-v1 realized-form disclosure contract: a dedicated rejection test exercising the realized-form substantive invariants (a disclosure must name a realized reference or value summary and use the matching processor/backend realization authority) and the run-level invariant that disclosure evidence refs must be listed in the run traceability evidence refs and must be duplicate-free, plus a schema-and-model invalid fixture for a processor-realized disclosure carrying a backend realization authority. The model and published schema shipped under #89; this change adds the conformance tests of record without changing them. (#239)- ### Added

  - Published SEM-214 meaning and comparability semantics for API-408 participant context views. (#247)- ### Added

  - Published SEM-216 boundary semantics distinguishing runtime-observable state, captured evidence, derived evaluations, analysis outputs, and audience-specific views over the existing contract families. Participant-visible context views drawing on archival `evidence_record` or `derived_measure` source layers must now declare a governed view rule and redaction policy and mediate the source through the transformation, and redacted or withheld evidence records must disclose redaction/loss at the schema boundary. (#248)- Added SEM-217 external knowledge binding effect semantics, including a typed classifier for annotation, alignment, refinement, and constraint effects over existing concept-authority and semantic-profile artifacts. (#249)- Added ASR-521 participant benchmark conformance preflight guardrails. (#331)- ### Added

  - Published SEM-224 observability plane separation semantics: a carrier-oriented plane classifier (`aces_sdl.observability_plane_semantics`) that assigns each claim-bearing observability/evidence artifact exactly one of the five named planes — scenario-native observability, authored evidence requirement, processor/backend operational observability, captured evidence, and derived analysis — by carrier role rather than by free-form strings such as `log`, `trace`, or `evidence`. The three claim-bearing experiment-core contracts (`experiment-capture-spec-v1`, `experiment-evidence-record-v1`, `experiment-derived-measure-v1`) now publish their plane as a portable `x-aces-plane` schema annotation sourced from that classifier. (#334)- Added SEM-225 run-level augmentation disclosures to `experiment-run-v1`, with validation for processor/backend authority, environment-visible carriers, participant-visible markings, comparability observer effects, and run-traced evidence provenance.
  Refactored the SEM-225 disclosure validator into focused helper checks so the published contract validation stays maintainable. (#335)- Added the SDL `evidence_requirements` section, validation, and schema support for authored data, evidence, and output capture obligations. (#337)- Added a read-only runtime control-plane operational summary for processor/backend apparatus monitoring and troubleshooting. (#338)- ### Added

  - Added typed SDL node runtime metadata for mounts, local control interfaces, process identity, package inventory, dependency manifests, and scanner-derived package vulnerability findings. (#354)- Add typed SDL runtime surfaces for observed process sets, runtime environment variables, Linux capability policy, restart policy, and container resource limits; support issue-only CI verification for no-requirement implementation branches. (#358)- Add typed SDL runtime surfaces for filesystem inventory, container host/security configuration, full mount metadata, and health observations, with TechVault runtime parity example coverage. (#363)- Add the SDL `source.build` container image build-provenance surface, expressing base image and digest, image layer chain, structured Dockerfile instructions, classified build arguments, copied source mappings, image-default configuration, source-input checksums, and attestation/verification status, with TechVault webapp parity example coverage (ADR-023). (#364)- Add the SDL `runtime.local_identity` surface, expressing the observed local identity database — `/etc/passwd` users (UID, primary GID/group, GECOS, home, shell, supplemental groups, and distinct disabled/locked/no-login status), `/etc/group` records, and structured sudo/sudoers grants — with provenance and stability classification, and TechVault webapp parity example coverage (ADR-024). (#365)- Add the SDL `runtime.network` surface, expressing observed container network
  realization facts — container hostname/domain identity; per-network endpoints
  with realized IP, prefix length, gateway, and MAC address; backend network and
  endpoint identifiers each with an explicit stable/ephemeral stability class;
  distinct stable-alias, observed-DNS-name, and backend-generated-DNS-name lists;
  observable backend network driver/IPAM detail; and host-published port bindings
  with host IP and host port — validated against switch-backed `infrastructure`
  networks, with TechVault webapp parity example coverage (ADR-025). (#366)- Add the SDL `runtime.applications` surface, expressing the participant-observable
  HTTP application route/API/UI inventory of a node service — per-route paths and
  HTTP methods, owning transport service, auth/session requirements, typed request
  inputs (path/query/header/cookie/form/JSON-body/uploaded-file), response status
  codes and content types, template/static asset associations, route-specific
  vulnerability placement, route-visible fixture secrets or diagnostic disclosures
  with sensitivity classification, and observable redirect/error-disclosure
  behavior — validated against same-node services, top-level `vulnerabilities`,
  and observed file inventory, with TechVault webapp parity example coverage
  (ADR-026). (#367)- Added an `init_process` descriptor to `RuntimeContainerConfiguration` so SDL can
  express that a container runs under a backend-injected init / PID-1 reaper (for
  example Docker Compose `init: true`, where PID 1 becomes `/sbin/docker-init`).
  The typed `RuntimeInitProcess` submodel records whether the reaper is enabled,
  its implementation and executable path, child-reaping intent, and optional
  redactable PID-1 argv evidence, kept distinct from observed process inventory.
  See ADR-027. (#384)- Added `seccomp_profile` and `security_opt` fields to
  `RuntimeContainerConfiguration`, letting the SDL express a container's seccomp
  posture and backend-native security options without conflating them with
  `privileged` (see ADR-028). (#385)- ### Added — Process-scoped Linux capability overrides on `RuntimeCapabilityPolicy`

  `Node.runtime.linux_capabilities` now accepts a `process_overrides` list of
  `RuntimeProcessCapabilityOverride` records, letting an inventory express a
  capability delta scoped to a single process or its descendant subtree
  without flattening the container-wide baseline. Each override identifies its
  subject via the existing `RuntimeProcessIdentity` selectors and asserts an
  `effective` / `add` / `drop` delta at `process` or `subtree` scope. The
  motivating case is a container where the entrypoint loads audit rules with
  `CAP_AUDIT_CONTROL` and then exec's `sshd` through
  `capsh --drop=cap_audit_control`, so the interactive shell subtree runs
  without `CAP_AUDIT_CONTROL` and cannot disable auditing. The design
  boundary is locked in ADR-030. (Closes #386.) (#386)- ### Added — SDL surface for SSH server configuration (`Node.runtime.ssh_servers`): typed forced-command, accept-env allowlist, scoped `Match` rules, and adjacent sshd directives (allow/deny users and groups, authentication methods, password / pubkey / TTY toggles, chroot directory, authorized-keys file). Implements ADR-031. (#387)- Add a first-class `runtime.database_services` surface to ACES SDL
  (ADR-029). Database logical state — engine, wire protocol and version;
  listener observations; logical objects (databases, schemas, tables);
  database-local roles; privilege grants; and provenance-bearing settings
  — is now typed, queryable runtime inventory instead of prose in
  `runtime.applications[].description`. A top-level relationship can model
  typed application-to-database access with a structurally validated
  `database_access` (`role_ref`, `auth_method`). (#388)- ### Added

  - Added `runtime.software_components` for node-scoped runtime software component identity below package-manager row granularity. (#395)- Added separate Claude Code and Codex ACES asset inventory capture skills that
  turn the participant-discoverable inventory methodology into runnable
  agent-level guidance. (#397)- ### Added

  - Added the scenario/delivery classification drift audit and remediation record, fixed the live runtime-scope wording drift in the SDL sections reference, and added structural coverage tests for issue #400. (#400)- Add the SDL `runtime.identity_authorities` inventory for provider-neutral directory, domain, realm, IdP, IAM, and federation identity semantics, with typed authority services, subjects, policies, relationships, unambiguous local and qualified semantic reference validation, module-import ref rewriting, generated schema coverage, documentation lineage, example coverage, and secret-bearing attribute redaction. (#401)- Added ACES-owned asset inventory methodology docs plus deterministic container
  evidence capture and Syft CycloneDX normalization templates to the ACES asset
  inventory capture skills. (#411)- `Node.runtime.service_manager_units` records observed service-manager (systemd) unit state — `load_state`, `active_state`, `sub_state`, `enabled_state`, `result`, optional `main_pid`, `unit_file_path`, redactable `exec_start`, and same-node `Node.services[]` refs — distinct from transport services, live processes, packages, content, and authored conditions. See ADR-035. (#418)- Add typed `Node.runtime.mail_services` inventory and `mail_access` relationship semantics for mail-server logical state. (#420)- Add `Node.runtime.file_services` runtime inventory for SMB/Samba (and a
  generalizable seam for NFS, FTP/SFTP, WebDAV, and object-store services),
  with typed shares, service-local passdb-style principals, portable
  subject/resource/action/effect/basis access rules, observed access
  outcomes, and qualified `nodes.<n>.runtime.file_services.<id>[...]`
  references for module composition. Extend `RuntimeFilesystemEntry` with a
  `presence` field (`present` default, `expected_absent`, `unknown`,
  `other`) so authored/expected paths absent at capture time retain their
  expected `entry_type` instead of collapsing to `other`. Implements
  ADR-037. (#421)- Added typed `Node.runtime.dns_services` inventory for DNS authoritative and
  resolver runtime state, including zones, RRsets, common typed RDATA, resolver
  policy, DNSSEC posture, dynamic-update posture, settings redaction, evidence
  refs, semantic validation, module-import ref rewriting, docs, and schemas. (#426)- Added node-scoped `runtime.security_monitoring_managers` inventory for SIEM/security-monitoring managers, including listeners, components, enrolled agents, agent groups, detection content sets, bounded settings, semantic validation, qualified relationship refs, and generated schema support. (#428)- ### Added

  - Added `runtime.network_sensors` for node-scoped NSM/IDS monitoring posture, including monitored network refs, capture metadata, validation, docs, and schema publication. (#429)- ### Added

  - Add typed SDL runtime inventory for IDS/NDR network detection engines. (#430)- Added `runtime.service_listeners` so SDL inventories can model observed bind
  addresses, ports, listener scope, process/service ownership, readiness evidence,
  and published-port correlations without overloading `Node.services`. (#431)- Added SDL support for parsed security-monitoring detection definitions beneath runtime security-monitoring managers, including validation-backed source, content-set, correlation, target, and canonical digest metadata. (#434)- ### Added - Registered the ACES gap-remediation implement overlay for Codex/Claude discovery and regression coverage. (#445)- Added the SCN-010 expressivity gap analysis (`docs/aces/inventory/scn010-expressivity-gap-analysis.md`): the peer-review-grade analysis of ACES SDL runtime-surface expressivity gaps found while holding the remaining APTL TechVault SCN-010 SOC-stack containers to the wazuh.manager parity depth bar, and the cohesive whole-SDL architecture that resolves them (requirements DSL-132 through DSL-139). (#449)- Add the SCN-010 `runtime.datastore_services` inventory family (DSL-132): a single
  `RuntimeDatastoreService` spine discriminated by an OPEN `data_model`
  (`search_index` / `wide_column` / `key_value` / `relational` / `unknown` /
  `other`) for the non-relational datastores (OpenSearch/Elasticsearch search
  clusters, Cassandra wide-column store, Redis key-value store) that the
  irreducibly-relational `runtime.database_services` cannot shape. A
  `require_profile_for_data_model` guard makes each data model's defining geometry
  (search shard/replica counts, wide-column replication strategy/factor, key-value
  persistence posture) executable so an under-populated instance fails validation.
  The family is registered in the runtime service-family registry, wired into
  `RuntimeConfiguration`, semantically validated (owning-service and delegated
  `authorization_ref` resolution against the same node), and published to the
  generated SDL schemas. (#450)- Add the SCN-010 `runtime.platform_applications` inventory family (DSL-133): a
  single `RuntimePlatformApplication` spine discriminated by an OPEN
  `platform_kind` (`threat_intel` / `soar` / `analyzer_engine` /
  `case_management` / `analytics_dashboard` / `unknown` / `other`) for the
  security platform applications (threat-intelligence platform, SOAR, analyzer
  engine, case management, analytics dashboard). Content objects are bounded
  parsed manifests (typed kind + bounded attributes + typed references +
  marking/evidence refs, never raw bodies). A `require_profile_for_platform_kind`
  guard makes each kind's defining content/binding profile executable so an
  under-populated instance fails validation. The family is registered in the
  runtime service-family registry, wired into `RuntimeConfiguration`, semantically
  validated (owning-service and delegated `authorization_ref` resolution,
  content-object `references` and `marking_refs` intra-application integrity), and
  published to the generated SDL schemas. (#451)- Add `runtime.app_authorizations` application-internal RBAC inventory (principals with credential classification, roles, resource-scoped permission grants, role mappings, and tenants) with reference validation and generated schemas (DSL-134). (#452)- Add `runtime.scheduled_jobs` cadence-and-run-state inventory (closed interval/cron/calendar recurrence plus observed last/next run and last result) with generated schemas (DSL-135). (#453)- Add `runtime.forwarding_agents` log-forwarding / intel-sync agent inventory (typed sources, transforms, ship targets, buffer policy, reload channels, and settings) with an executable `require_profile_for_agent_kind` guard, scenario-scoped ship-target node/service ref resolution, enrollment-identity and secret-setting redaction, and generated schemas (DSL-136). (#454)- Add `runtime.orchestration_authorities` container-spawn authority inventory (engine, scope, spawn templates, lifecycle policy, realized children, and privilege class) with an executable `require_profile_for_privilege_class` guard and scenario-scoped `control_interface_ref` resolution that requires a read-write docker socket for `host_root_equivalent` authorities, plus generated schemas (DSL-137). (#455)- Wired three typed relationship subtypes into the top-level `Relationship` model
  (DSL-138): `forwarding_edge` (`RelationshipForwardingEdge`),
  `service_integration` (`RelationshipServiceIntegration`), and `proxy_upstream`
  (`RelationshipProxyUpstream`), mirroring the existing `database_access` /
  `mail_access` typed exceptions. The semantic validator now cross-references each
  subtype's refs (forwarder, consumer/engine and auth principal, route and
  upstream node/service) and enforces two agreement guards: a forwarding edge's
  `target_listener_role`/`protocol` must be consistent with at least one of the
  agent's ship targets, and a proxy upstream's shared facts (target node, target
  service, TLS-termination boolean) must agree with the referenced route's
  `upstream_target` so the same fact recorded at two scopes can never silently
  contradict. See ADR-052. (#456)- Add scenario-level forwarding agents for off-node sidecar forwarders, with typed `forwarding_edge` resolution across node-hosted and scenario-level registries (DSL-140). (#460)- Added typed datastore cluster and partition fields for native UUIDs, document counts, deleted-document counts, byte-normalized store sizes, creation timestamps, and open/closed status. (#468)- Add structured `runtime.datastore_services` mapping and template manifests so search-index schemas can carry bounded field counts, dynamic policy, digests, and evidence refs instead of name-only lists. (#469)- Added DSL-141 datastore-node engine provenance to `runtime.datastore_services`: typed `engine_version`/`build_hash`/`build_type`, JVM heap byte bounds and `memory_locked` posture, a per-node `RuntimeDatastoreEnginePlugin` inventory carrying per-plugin versions, and a product-neutral `RuntimeDatastoreNodeEndpoint` (client/peer) listener inventory — replacing the name-only service-level `engine_plugins` list and the single ambiguous node `address`. (#470)- ### Added
  - Add an ADR amendment policy (ADR-059) and an acceptance-content pin gate: `docs/decisions/adrs/adr-index.yaml` pins every accepted ADR's canonical-content `sha256`, and `tools/check_adr_immutability.py` (wired into the `policy` nox session) fails when an accepted ADR changes without a recorded `## Amendments` entry or a superseding ADR. Reconciled the already-amended ADRs (025, 029, 032, 038, 041, 048, 050, 052) with honest amendment records so the gate starts green. (#481)- Added an assurance fulfillment gate (`specs/formal/assurance-fulfillment.yaml`, enforced by `tools/check_assurance_policy.py` via `nox -s policy`): every classified formal-spec subsystem must deliver — or explicitly waive with an ISO date and tracking reference — each verification artifact kind required by its FM level, so a subsystem can no longer be classified FM3 with no executable artifacts while CI stays green. (#485)- Added an executable participant-semantics invariant oracle covering I1-I18 with property-based valid progressions and targeted rejecting mutations. (#487)- Carry the SEM-218 explicitness class through processor compilation as typed realization-requirement metadata on the runtime model, and add a planner realization-support gate that rejects an unrealizable exact (or unsupported constrained) requirement against the selected backend's `realization_support` with a structured diagnostic instead of silently approximating it (invariants I1/I2/I4). (#490)- Added the SEM-218 runtime non-approximation gate (invariant I2) at the backend-adapter boundary, which rejects a backend that silently realizes an exact author declaration with a weaker value, and the `realization_provenance` ledger (invariant I5) on the runtime snapshot envelope, which records each realized concern's explicitness class and author-declared / processor-derived / backend-realized origin in published schemas, fixtures, and the schema-publication manifest. (#491)- Added a normative definition of "surface" to the concept-authority specification — including the one-surface-versus-two decision rule from ADR-033 — with a derivative glossary entry that points back to it; and classified the agent-usable guidance profile (`specs/agent-guidance/agent-guidance.yaml`, AUT-811) as a `governance-guidance` artifact through a new `normative_artifact_families` block in the authority-boundary manifest, enforced by `tools/check_authority_boundary.py`, so its authority class is decidable from the manifest alone. (#494)- Added the UCO alignment evidence contract (`uco-alignment-v1`): a machine-checkable mapping from every adopted/adapted cyber-domain concept family to the UCO object types it aligns to, with the reviewed UCO version pinned, adapted-family divergences enumerated explicitly, generated JSON Schema, valid/invalid fixtures, and catalog-derived coverage validation. (#495)- Added a concept-authority catalog governance gate (ADR-062, `tools/check_concept_authority_governance.py`, wired into the `policy` nox session): every concept family in `concept-families-v1.json` must be ADR-linked, and inline-code cross-references in a family's `relation_rules` must resolve to a known concept family or controlled vocabulary. (#496)- Add the normative, language-neutral SDL authoring specification under `specs/sdl/`: a catalog set covering the document model, the top-level section catalog (reconciled to the live `sdl-authoring-input-v1.json` contract), the cross-section reference-resolution catalog, the variable/instantiation catalog, the node-scoped runtime-family index, and the error-vs-advisory diagnostics boundary. The specification is registered as a `prose` authority root in `specs/authority/authority-boundary.yaml`, giving independent implementations a structural authority that does not require reading the reference Python. (#498)- The worked SDL examples under `examples/scenarios/` are now validated against the published `sdl-authoring-input-v1` JSON Schema in CI, proving the shipped example corpus conforms to the contract surface downstream consumers read (previously only Pydantic-parser acceptance was checked). Includes a non-vacuity corpus guard and a negative control so the suite cannot pass vacuously. (#501)- The `aces conformance backend` suite now has end-to-end proof tests: a realistic stub backend manifest passes against the canonical `contracts/fixtures` corpus under a full runtime-contract profile, and two seeded-violation tests copy the corpus to a temp tree, corrupt a required field in a required contract fixture (the backend manifest and a deep participant-episode runtime contract), and assert the runner exits non-zero while naming the offending contract. This demonstrates a caught contract violation rather than only a missing-fixture failure, backing the conformance CI claim in `docs/explain/reference/backend-conformance.md` (ASR-502). (#502)- Add a determinism witness for the SDL parse/instantiate/compile pipeline: it compiles representative scenarios (including a module-import scenario) twice, and once more under a varied PYTHONHASHSEED in a subprocess, and asserts the compiled output is byte-identical. docs/explain/sdl/parser.md now cites it. (#506)- Added a related-work comparison page (`docs/explain/sdl/related-work-comparison.md`)
  positioning ACES against precedent systems — OCR SDL, CybORG, CACAO, SISO Cyber
  DEM/FOM, and academic range DSLs (CRACK/KYPO/CyRIS) — across eight expressivity
  dimensions. Every non-ACES cell carries a primary-source citation, and the page
  states explicitly where the precedents lead ACES. Linked from the README Lineage
  section and `lineage.md`, which gains a Cyber DEM/FOM differentiation subsection. (#508)- The published contract corpus (backend/semantic profiles, the fixture conformance corpus, concept-authority catalogs, and schemas) now ships as package data in the `aces-sdl` wheel and sdist and is resolved through a single `importlib.resources`-backed seam (`aces_contracts.corpus`), so `aces conformance backend` and SDL semantic validation work from an installed distribution with no source checkout. The top-level `contracts/` tree remains the normative authority; `--fixtures-root` / `--profiles-root` overrides are unchanged. Added a `v*`-tag release workflow that builds the corpus-bundled artifacts and publishes a GitHub Release so downstream backends can pin a version instead of a `dev` commit SHA. (#537)- Added a repository-side PR title guard (`.github/workflows/pr-title-lint.yml` backed by `tools/check_pr_title.py`) that rejects agent-branded PR title prefixes such as `[codex]`, `[claude]`, `[openai]`, and `[chatgpt]`, and enforces the conventional `<type>(<optional-scope>): <subject>` shape with a lowercase-leading subject on every target branch including `dev`. The same validator powers local tests so the policy cannot silently drift from the workflow. (#567)- Added a focused enterprise reference SDL scenario for authored participant action, observation-boundary, Wazuh evidence, policy provenance, and runtime/backend handoff. (#598)- Added a participant action-admission binding path that lets runtime backends record SDL-declared participant behavior through a selected participant implementation, including a request DTO control-plane surface. (#599)- Add the cross-backend evidence corpus producer (`aces corpus build`) that pairs the
  libvirt reference-backend scenario-evidence run with the APTL realization of the same
  authored scenario and derives a cross-backend **invariant ledger**
  (`aces.cross-backend-evidence-corpus/v1`, a thin local artifact). The ledger records
  preserved invariants (authored scenario digest + compiled ACES address sets +
  recorded evidence surfaces, each with a per-backend basis), realization differences,
  unsupported/degraded surfaces, and evidence limitations. The libvirt run is consumed
  through the existing `aces.libvirt.scenario-evidence-run/v1` producer in deterministic
  mode; the APTL run is a bounded, honestly-labeled summary + link to
  Brad-Edwards/aptl#558, with an optional `--aptl-evidence` path that ingests only
  allowlisted portable fields from a supplied APTL export (no APTL-private data). The
  committed corpus lives at `examples/corpus/reference-demonstration/` and is drift-tested. (#600)- ### Added

  - Added a provisioning-only `aces_backend_libvirt` package with libvirt/QEMU target construction, manifest wiring, invalid-plan diagnostics, fail-closed driver confirmation checks, and an injected libvirt driver boundary.
  - Tightened the libvirt backend type and reconciliation helpers so SonarCloud accepts the new backend surface.
  - Validated the TechVault scenario through dynamic instantiation, planning, and libvirt provisioning, including switch-backed network links.
  - Added the full TechVault operational scenario and libvirt provisioning coverage for its 30-node, four-network SOC/enterprise/red-team surface.
  - Added APTL-style reduced TechVault scenario variants and native libvirt coverage proving they realize distinct ACES-derived domain/network/service surfaces.
  - Added `aces libvirt techvault validate-live`, which boots TechVault scenarios as native libvirt/QEMU initramfs appliances, verifies the independent substrate, service readiness, Kali-shared-network reachability, SOC readback, clean-boot recomposition, and run-archive evidence.
  - Added an `aces_operations` package for live operational gates so the CLI can invoke TechVault parity checks without crossing backend/runtime ownership boundaries directly.
  - Hardened the TechVault live gate implementation structure so SonarCloud complexity checks stay green while preserving the SOC readiness and evidence checks. (#601)- ### Added

  - Published the libvirt/QEMU provisioning-only `backend-manifest-v2` as a conformance-verified acceptance bar: the manifest validates against the checked-in `backend-manifest-v2` JSON Schema, `supported_contract_versions` covers the published provisioning-only profile contract set, and `realization_support` declares a non-hollow realization envelope (node-type and os-family only — no content or account over-claim, matching what the libvirt interpreter actually realizes). (#602)- ### Added

  - The libvirt/QEMU backend now fully and dynamically realizes provisioning plans: node resources become libvirt domains (base image + a NoCloud cloud-init seed), network resources become libvirt networks with real `ip`/`dhcp` addressing, and `account-placement`, `content-placement`, and `feature-binding` resources are realized into the target domain's cloud-init. Account realization covers every governed feature (groups, shell, home, disabled, auth_method, mail, spn, authorized SSH keys); content realization covers file/dataset/directory; and feature/service and mail realization is **OS-family-aware** — Linux (`systemctl`/`apt`), FreeBSD (`sysrc`/`pkg`), Windows (`choco`/`sc.exe`), and macOS (`brew`) each get their native mechanism, with a portable descriptor as the substrate ceiling for families and terms (e.g. Kerberos SPN without a domain) that no generic host can realize further. Node network ACLs are realized host-side as libvirt **nwfilter** rules referenced from the domain interface (OS-independent enforcement). `apply()` is idempotent against the `RuntimeSnapshot` (UNCHANGED operations never touch the host), and a placement change realizes its target domain even when the node itself is UNCHANGED (the seed now carries different cloud-init). For the CREATE/UPDATE operations that do reach the driver it **converges** existing host objects (stop + undefine, then redefine the desired XML/seed/nwfilter) so a tightened ACL, a disabled account, or a changed seed is genuinely enforced rather than skipped, with no duplicate resources and with seed and nwfilter cleanup on destroy. Convergence, deletion, and host-global nwfilter redefinition are all ownership-checked: each domain, network, and nwfilter carries a deterministic per-address libvirt UUID, and an existing object that shares a name but is not the ACES object for that address is never destroyed, undefined, or overwritten — apply fails closed. The NoCloud `instance-id` is derived from the rendered seed content, so a converged UPDATE with changed content re-runs cloud-init in the guest instead of being treated as already consumed. The backend manifest declares the full governed provisioning vocabulary it realizes — all content types, all account features, accounts, ACLs, and the `macos` OS family — superseding the earlier "provisioning-only, node-type and os-family only" capability surface; "provisioning-only" now means domain scope only (no orchestrator/evaluator/participant runtime).
  - Realization is **fail-closed** at every governed-value boundary so a claim can never exceed what is enforced: an ACL whose action/protocol/direction is unrecognized, whose port is invalid, whose port scope is paired with a non-`tcp`/`udp` (wildcard) protocol, or whose `from_net`/`to_net` does not resolve to a concrete CIDR is rejected with an ERROR diagnostic instead of widening into a broad allow; a placement that cannot be bound to a node in the plan fails the apply rather than being silently dropped; a password account is never unlocked without rendered credential material (key-based accounts get their authorized keys and stay password-locked); and plan-controlled identifiers interpolated into `/etc/aces` descriptor filenames are reduced to a single safe path component so a crafted account/feature/content name cannot traverse out of its descriptor directory (the content-placement `path` remains the one intentional arbitrary-write surface). Cloud-init `runcmd` entries are emitted in argv-list form (cloud-init runs them without a shell) so plan-derived paths and package names cannot inject shell commands into the root-applied guest config. Seed media is written into a freshly created, owner-verified workspace with `O_NOFOLLOW`/`O_EXCL` exclusive `0o600` writes (a pre-positioned symlink or file cannot redirect or capture rendered content); the seed directory is `0o711` (traversable, not listable) and the seed ISO is `0o600` — never world-readable — so the rendered cloud-init stays private while the libvirt/QEMU process reaches it through libvirt's dynamic-ownership relabel of the attached disk. Real libvirt/QEMU realization is exercised only on a host with the daemon; default verification stays hermetic through injected seed-builder and connection seams. (#603)- ### Added

  - libvirt backend: emit typed, blocking capability diagnostics
    (`libvirt-backend.realization.unsupported-{node-type,os-family,content-type,account-feature}`)
    when a provisioning plan requires a node type, OS family, content type, or
    account feature outside the backend's declared manifest envelope. The backend
    now fails closed on out-of-envelope terms instead of silently or partially
    realizing them, consistent with the processor's manifest capability checks. (#605)- Added a libvirt backend participant runtime for the reference scenario. `create_libvirt_manifest(participant_runtime=True)` now declares `ParticipantRuntimeCapabilities` (red role, behavior features disclosed as `disclosed_weak`) plus the required participant episode/behavior contract versions, and the libvirt target provides a `LibvirtParticipantRuntime` driven through `RuntimeControlPlane`. The shared RUN-311 episode lifecycle is factored into `BaseParticipantRuntime` (reused by the reference and stub backends), and libvirt's action leaf routes through a pluggable `LibvirtParticipantDomainAdapter`; the default `DeterministicParticipantDomainAdapter` needs no live libvirt daemon and discloses that limitation in the emitted participant-implementation provenance. Without the flag the backend stays provisioning-only. (#614)- Add the libvirt evidence-run evaluator-evidence producer
  (`aces libvirt evidence validate`) that composes the libvirt participant
  runtime, native substrate realization, backend manifest, and
  experiment/evaluation contracts into a stable, validated, redacted
  `aces.libvirt.scenario-evidence-run/v1` run artifact for the enterprise
  participant/evidence scenario, feeding the Brad-Edwards/aces#600 cross-backend
  invariant ledger. (#615)- Added the accepted CAGE-2 replication architecture ADR and companion design
  record for REP-001. (#635)- Documented the proposed realization-envelope semantics, including prior art,
  manifest carriage, subsumption, witness generation, and negative conformance. (#667)- Add ADR-073 (proposed) examining whether OCR-inherited SDL scoring
  (`metrics`/`evaluations`/`tlos`/`goals`) and the CybORG `agents.reward_calculator`
  label belong in ACES, with scoring-scope research notes
  (`docs/research/scoring-scope/`) and a SEM-206 assessment-semantics compatibility
  guardrail. The ADR recommends treating these surfaces as vestigial against the
  experiment-vs-data-use boundary (ADR-055/064/069) and defers the decision to
  review. (#671)- `aces-sdl` is now published to PyPI (`pip install aces-sdl`). Releases are cut from a single committed `__version__` literal, bumped from the towncrier changelog fragments by `tools/release.py` (`removed` → major once ≥ 1.0 else minor, `added`/`changed`/`deprecated` → minor, `security`/`fixed` → patch; `breaking` is recorded but forced manually). Merging the release PR to `main` builds the corpus-bundled wheel + sdist, publishes over OIDC trusted publishing, and attaches a CycloneDX SBOM to the GitHub Release. (#684)- - Added a README lineage section listing the main prior-work influences behind
    ACES.- Adopted `towncrier` changelog fragments so PRs add release-note snippets under `changelog.d/` instead of hand-editing `CHANGELOG.md`.- Noted in the README that APTL (Advanced Purple Team Lab) is a worked example of a separate project specifying its scenarios as ACES SDL documents and realizing the selected topology on a concrete Docker Compose backend.

### Changed

- Split the oversized `aces_sdl.validator` module (4,139 lines) into a package of per-validation-seam mixin modules (`_core`, runtime families, relationships, content/objectives, workflows, sections), each under the ADR-015 600-line cap, behind an API-stable `SemanticValidator` re-export, and reduced the per-pass cyclomatic/cognitive complexity of the moved validators by extracting focused helpers and shared context objects. Pure refactor: no validation behavior, diagnostics, pass ordering, or public-API change. The `validator.py` entry is removed from the oversized-source allowlist. (#42)- Migrated the backend conformance suite and CLI onto the published
  contracts tree: `contracts/profiles/backend/*.json` is now the single
  authority for profile-to-contract requirements (loaded via the new
  schema-published `aces_contracts.backend_profiles.BackendProfileModel`,
  which carries a `schema_version` field, is registered in `schema_bundle()`,
  ships as `contracts/schemas/profiles/backend-profile-v1.json`, and is
  validated end-to-end by `tools/check_json_artifacts.py`), the in-code
  `_PROFILE_REQUIREMENTS` duplicate authority has been removed, the
  `full-remote-control-plane` profile now declares the participant-episode
  contracts it actually validates, and `aces conformance backend` is the
  canonical Typer CLI entry point with a thin
  `python -m aces_conformance.runner` compatibility delegate. The runner
  and CLI accept any profile id discoverable from the JSON corpus (not
  just the four known `BackendCapabilityProfile` enum members); known
  runtime surfaces continue to drive capability-gap and live-probe
  behavior for the four families this implementation understands, and
  target conformance refuses unknown profile ids with a structured
  `conformance.profile-runtime-surface-unknown` diagnostic. Profile-load
  failures (missing file, malformed JSON, schema-rejected payload, swapped
  identity) surface as structured `conformance.profile-load-failed`
  diagnostics — with sanitized error text that does not echo rejected
  payload contents — at every public surface, and CLI JSON diagnostics
  now carry full `code`/`domain`/`address`/`severity` so downstream tooling
  can dispatch on codes without parsing prose. The shared loader rejects
  profile ids that don't match `^[a-z0-9]+(?:-[a-z0-9]+)*$` before
  constructing a filesystem path, and the override path additionally
  confines the resolved profile path under the supplied `profiles_root`. (#66)- Added experiment-run observability/evidence conformance diagnostics for run-level augmentation disclosures and evidence-requirement refinements. (#128)- Tightened SEM-215 outcome interpretation scope plus runtime provenance and event-grounding checks for benchmark, episode-status, action-outcome, evidence, and terminal participant-episode-history inputs. (#191)- Require API-411 participant outcome reports to carry at least one explicit state relationship in the published contract model and generated schema. (#203)- Added a runtime-snapshot conformance gate requiring participant behavior history to be tied to a compiled participant behavior binding before history is accepted. (#204)- Added SDL `behavior-specifications` for first-class participant behavior aggregates with validation, compiler output, schemas, docs, and examples.

  Refactored the behavior-specification semantic reference checks to keep the SonarCloud maintainability gate clean without changing validation behavior, including grouping the private reference-index inputs used by the validator. (#206)- Added a validated AUT-806 example, template, and pattern library covering scenarios, workflows, participant behavior, tasks, runs, and studies. (#227)- Documented and test-backed DSL-123 scenario-native observability reference coverage. (#336)- Document the ACES asset-inventory issue-template fragment and reconcile the
  methodology closeout notes for ACES #353. (#353)- Clarified the SDL scenario/delivery boundary for runtime node state and added
  redaction classifications for runtime mount sources/options and local-control
  bind sources so host-local details can be withheld by contract. The generated
  SDL JSON Schemas now carry matching conditional guards for those redacted raw
  values across parser-normalized sensitivity label spellings, and ADR-033
  documents the ACES-native basis, explicit cross-repo downstream APTL limits, and
  the claim scope for adjacent academic and standards sources behind the design. (#399)- Split live runtime control out of `aces_processor` into the new `aces_runtime`
  package, added policy enforcement for SDL/processor/runtime module boundaries,
  documented the new architecture in ADR-036 and the API reference, tightened
  the boundary gate to fail closed under pre-commit/CI, and removed built-in
  control-plane principals from strict defaults. Shared runtime/backend DTOs now
  live in `aces_contracts`, backend protocol signatures are typed against those
  contracts, module-boundary policy covers every first-party package root, and
  proxy identity headers require explicit opt-in. (#410)- Added a required `control_interface_id` to `RuntimeControlInterface` so local control interfaces carry a stable, reference-able id (DSL-137). The id is symbol-validated (no empty or `${var}` placeholder) and is enforced unique across a node's `local_control_interfaces`. Generated SDL contract schemas were regenerated accordingly. (#455)- Renamed the runtime service-family inventory models `SshServerConfig` and `DatabaseService` to `RuntimeSshServer` and `RuntimeDatabaseService` so every runtime service-family model follows the uniform `Runtime<Noun>` class-name invariant (DSL-139). The generated SDL authoring and instantiated schemas reflect the new `$defs` names.

  Unified the five drifted per-family secret-bearing setting-name detectors (database, DNS, directory-identity, mail-service, security-monitoring) into a single shared `name_indicates_secret` helper in `runtime_values`, backed by the de-duplicated union of every family's token set (`SECRET_NAME_TOKENS`) plus the alphanumeric-part match (`SECRET_NAME_PARTS`). Detection is now a strict superset across all runtime families, closing gaps where one family would redact a secret-bearing setting name that another would have let through.

  Renamed the seven forked runtime service-family primary identifiers to the uniform `singular(collection) + "_id"` rule (DSL-139 / #443): `RuntimeServiceListener.listener_id` to `service_listener_id`, `RuntimeIdentityAuthority.authority_id` to `identity_authority_id`, `RuntimeFileService.service_id` to `file_service_id`, `RuntimeMailService.service_id` to `mail_service_id`, `RuntimeNetworkSensor.sensor_id` to `network_sensor_id`, `RuntimeNetworkDetectionEngine.engine_id` to `network_detection_engine_id`, `RuntimeSecurityMonitoringManager.manager_id` to `security_monitoring_manager_id`, and `RuntimeSshServer.server_id` to `ssh_server_id`. Child-collection identifiers of the same spelling are unchanged, and the generated SDL authoring and instantiated schemas reflect the new field names.

  Removed the redundant scalar `RuntimeConfiguration.process` twin (DSL-139 / #443); a single observed process is now expressed as a one-element `processes` list. The generated SDL authoring and instantiated schemas drop the `process` field, and the runtime service-family structural-invariant lint now enforces an empty `KNOWN_VIOLATIONS` set across the whole surface.

  Migrated the runtime mail-service validators in-class to match every other runtime family (DSL-139 / #442): `RuntimeMailService` model-local duplicate/cross-field checks are now private `@model_validator(after)` methods, and the scenario-level mail-service and relationship `mail_access` cross-reference checks are now `SemanticValidator._verify_*` methods rather than free functions wired specially from `validate()`. Validation behavior is unchanged.

  Reconciled the runtime service-family enum surface to the enum-sentinel convention (DSL-139 / #443): every observed-value runtime enum now carries both `unknown` and `other` (open taxonomy) and closed structural/protocol/redaction-lattice vocabularies carry neither, eliminating the single-sentinel state where an enum carried exactly one of the two. Forty-nine single-sentinel runtime enums were made open by additively appending the missing sentinel (no existing value or default changed), and the generated SDL authoring and instantiated schemas reflect the new enum values. An executable drift guard (`test_runtime_enums_open_or_closed_not_single_sentinel`) now fails on any future runtime enum introduced in a single-sentinel state. (#457)- ### Changed

  - Centralize runtime observed-value redaction rules and enforce secret-bearing
    raw-value omission across environment, image-default, exposed-field, and
    setting surfaces. (#463)- ADR corpus policy now validates the canonical ADR template's required sections. (#482)- ### Changed

  - Added an auditable FM classification ledger and policy gate for new ADR
    classification fields. (#483)- Added executable participant-runtime invariant oracle evidence for ADR-054 / ASR-505. (#486)- Add SEM-218 explicitness classification metadata to SDL validation and preserve authored exact/constrained/open classes through instantiation, including helper traversal paths that keep downstream metadata derivation consistent. (#489)- Added a native `episodes` concept family with participant-runtime lineage,
  semantic-profile coverage for participant episode contracts, and tests that
  anchor episode-keyed contracts to the shared concept authority. (#492)- Added a native `runtime-inventory` concept family and a `scenario-node-runtime`
  reference model for `nodes.*.runtime`, with authoring-phase semantic-profile
  coverage, an extension-governance decision path for runtime fields, and
  reference-model binding resolution for nullable-optional schema surfaces. (#493)- Published schema evolution is now governed by an ADR-backed manifest policy:
  current schemas are marked draft with canonical content hashes, and stable
  schemas cannot take incompatible in-place structural changes without a version
  bump. (#497)- Flipped published-schema authority per ADR-009 §7: `contracts/schemas/` is now the hand-governed normative authority, `tools/check_generated_schemas.py` proves the reference implementation generates an identical bundle without overwriting the published schemas, and a manifest change-ledger (`schema-publication-manifest.json` `last_change` for added/modified schemas and `removed_schemas` tombstones for deletions) plus the `schema-change-missing-manifest` policy rule require a contract-facing description for any schema change, including removals. (#499)- The published `instantiated-scenario-v1` contract now rejects unresolved `${var}` substitution tokens in string values — both whole-string placeholders (`"${os}"`) and embedded tokens (`"host-${index}"`) — differentiating it from `sdl-authoring-input-v1`, which still accepts them. The same invariant is enforced on the `InstantiatedScenario` model so directly constructed instances must be fully concrete. (#500)- The SEM-200 semantic-coverage gate (`tools/check_semantic_coverage.py`) now verifies integration, not just existence: an `active` row whose named tests import none of its realizing Python modules, or whose named test files contain a zero-assertion `test_*` stub, fails `nox -s policy`. Import resolution recognizes compatibility wrappers and package re-exports. Adds a read-only `--report` mode that lists construct families by status with per-row test and module-coverage counts to surface thin coverage. (#504)- State the SDL error-vs-advisory boundary normatively in `specs/sdl/diagnostics.md` §5, resolving the classification previously deferred to review IMP-3. The criterion is meaning preservation: an error affects SDL meaning (structural/semantic invariants — reference resolution, uniqueness, ambiguity, acyclicity, required-profile guards, instantiation, explicit redaction), while an advisory is a deployability or quality heuristic that leaves SDL meaning intact, with a fail-closed default for borderline cases. `docs/explain/sdl/validation.md` now cites that single normative source instead of restating the rule, and a new AST drift-guard test enforces that the reference `SemanticValidator` keeps the advisory (`_warn_*`/`_collect_advisories`) and error (`_verify_*`/`_err`) channels separate. (#505)- ### Changed

  - Hardened the participant-semantics and participant-runtime literature
    lineage with the missing primary theory: interpreted systems and dynamic
    epistemic logic for information states and view transitions, Kuhn's
    extensive-form information sets and perfect recall, Goguen-Meseguer
    noninterference and Sabelfeld-Sands declassification for the hidden-truth
    boundary, STRIPS/PDDL/PDDL2.1/PPDDL/RDDL for precondition/effect contracts,
    the Oliehoek-Amato Dec-POMDP monograph, mean-field game theory,
    Fidge/Mattern vector time with the Schwarz-Mattern causality survey for the
    `VectorClock` ordering basis, Winskel/Mazurkiewicz partial-order
    concurrency, Allen/Koymans/Alur-Dill temporal formalisms, and
    Chockler-Halpern responsibility for multi-cause attribution. Corrected the
    PettingZoo/OpenSpiel contribution attribution (including in ADR-054's
    context), the CyGIL title conflation, the CRACK venue, the Dec-POMDP
    complexity authors/venue, the HLA edition, and grounded the CybORG
    sim-to-emulation claim in Standen et al. (2021). (#511)- ### Changed

  - Formatted the native TechVault libvirt live-gate helpers after splitting the QEMU appliance builder and probe/readback code into dedicated modules, and added explicit VM resources to the reduced TechVault scenario variants. (#601)- Backend target conformance now runs a backend-neutral live provisioning probe
  that proves real snapshot mutation for provisioning-only backends (including
  libvirt/QEMU) — succeeded provisioning status, changed addresses, and at least
  one provisioning-domain snapshot entry — so a backend can no longer pass target
  conformance on manifest/contract-surface validation alone. Adds a daemon-free
  recording libvirt driver for hermetic verification and a committed libvirt
  `provisioning-only` conformance report. (#606)- Renamed the `paper-*` reference-scenario, evidence-run, and corpus identifiers to
  functional names, decoupling the ACES repo from any specific publication. The
  scenario is now `examples/scenarios/enterprise-participant-evidence-loop.sdl.yaml`;
  the libvirt producer is `aces_operations.libvirt_evidence_run` emitting
  `aces.libvirt.scenario-evidence-run/v1`; the corpus producer is
  `aces_operations.cross_backend_corpus` emitting `aces.cross-backend-evidence-corpus/v1`.
  The CLI command `aces libvirt paper validate-evidence` is now
  `aces libvirt evidence validate` (`aces corpus build` is unchanged). The committed
  demonstration corpus was removed from this repo — the producer remains, and the
  canonical published corpus now lives in the public `Brad-Edwards/research` repo. (#670)- Clarified the ACES acronym expansion in the README introduction.- Dedupe the SDL module-import symbol-index hashmap-section list (now lives in `_module_symbols.py` and is re-exported to `composition.py`) and extract a shared `_verify_step_terminator_and_compensation` helper in the SDL semantic validator so OBJECTIVE and CALL workflow steps share one terminator/compensation pass instead of two near-identical inlined copies. Pure code-quality cleanup; no behavior change.- Internal refactor to clear the SonarCloud `new_violations` quality gate on the `dev → main` integration PR: split four oversized source files into focused modules — `aces_contracts/participant_behavior.py` (enums/tables → `_participant_behavior_types.py`), `aces_sdl/validator/_runtime_platform.py` (orchestration-authority checks → `_runtime_orchestration.py`), `aces_sdl/validator/_relationships.py` (proxy-upstream checks → `_relationships_proxy.py`), and `aces_sdl/runtime_datastore_partitions.py` (node child models → `runtime_datastore_nodes.py`, shared helpers → `_runtime_datastore_support.py`) — and reduced the cognitive complexity of `ParticipantHistoryViewModel._validate_nested_record_scope` plus a returns-count refactor in `runtime_values.name_indicates_secret`. No behavior change; all public APIs are preserved by re-export.- Updated repository URLs and project metadata for the move to `autarchy-ai/aces`.

### Fixed

- Added an authoritative schema publication manifest and verification gate for the current `contracts/schemas/` tree. (#65)- Restored the example-scenario leg of the validation corpus and closed a related runtime-planner gap surfaced by the test-quality review. The MCP-server tests now exercise the curated `examples/scenarios/` SDL files through the MCP tool flow instead of silently skipping when the path resolved to a non-existent directory. The runtime planner now enforces `allowed_values` against backend `supported_os_families` and `max_total_nodes` even when the variable carries a default; previously the compile step substituted defaults before the planner could see the variable reference, so the capability check at `aces_processor/planner.py` was unreachable. (#67)- Refactored SEM-208 participant behavior validation and runtime compilation to clear SonarCloud maintainability findings. (#185)- Fix SEM-210 runtime conformance so visibility transition anchors are participant-local, participant behavior histories reject outer/inner participant mismatches, episode-close disclosures resolve to participant episode history, and observation-time visibility only applies transitions whose anchors have occurred. (#187)- Clarified SEM-211 participant behavior-history validation documentation to mention action-result reference authorization when compiled observation boundaries are supplied. (#188)- Participant runtime capability declarations now reject duplicate values and require published contract evidence during conformance. (#199)- Refactored ACT-607 authority-scope runtime address resolution helpers to clear SonarCloud maintainability findings without changing compiler behavior. (#207)- Avoided unnecessary iterable materialization in the agent guidance helper. (#225)- Refactored runtime mail-service semantic validation to satisfy SonarCloud maintainability checks. (#420)- ### Fixed

  - Addressed SonarCloud maintainability findings in the DNS runtime inventory implementation. (#426)- ### Fixed

  - Consolidated runtime service-family registration so public exports, module namespacing aliases, and semantic runtime refs share one registry, including `ssh_servers`. Accepted `provenance` on runtime identity attributes as a checked synonym for the existing origin enum to keep TechVault capture facts lossless. (#441)- Consolidated runtime validation helper policy and backfilled mail validation documentation plus ADR gate coverage for the runtime SDL consistency work. (#442)- Tightened typed runtime relationship validation so proxy-upstream service refs resolve to real upstream services and service-integration auth principals resolve within the engine application's authorization store. (#456)- Removed name-derived raw-value omission from runtime SDL observed-value
  validators so credential-shaped values remain realizable scenario content unless
  they are explicitly classified as `redacted` or `operator_secret`. (#471)- Added named semantic regression tests for composition-readiness and objective-window invariants. (#488)- Added a cross-family runtime invariant lint that prevents documented required-profile discriminators from shipping without registered Pydantic guard wiring. (#503)- Tightened citation hygiene across the SDL lineage and precedent documentation: expanded a bare-DOI citation to a full inline author-title-venue reference, snapshotted a Zotero-only preprint citation into a repo-tracked `docs/research/primary/` page so it is verifiable from the repository alone, relabelled the SCN-010 expressivity gap analysis's review process honestly (architect-guided adversarial self-review rather than an external peer-review panel), added a Syntax/Semantics/Both ("Borrowed") column to the design-precedent tables, sharpened the OpenC2 lineage boundary (command/response principle borrowed, payload/target structures not adopted), and added a research-corpus and citation-verification-scope note to the SDL limitations. (#509)- ### Fixed

  - Closed the participant-runtime formal-spec defects found in the 2026-06
    review: `mapping_loss` is now a closed vocabulary (with
    `mapping_loss_detail`); `LifecycleEnvelope` carries the
    attribution-edge and outcome-interpretation references its overview names
    (SEM-212/SEM-215 cross-ref); the declared delivery point is defined and
    carried (`delivery_basis`, `delivery_point_ref`, `delivered_at`) and the
    visible-history projection binds to it; stable redaction tokens have a
    declared stability scope; rollback/supersession can never rewrite
    participant-visible history; marking enforcement and visibility projection
    compose deny-first; `ClassificationClaim` defines when
    `event_classification`/`source_status` may be null; fully opaque
    participants have a defined minimal observable trace; the capability meet
    is total over affecting components (missing declarations contribute
    `unsupported`, never skipped); and reconstruction algorithm/proof refs must
    resolve through a versioned reconstruction registry. (#512)- ### Fixed

  - Corrected the shared-semantic-integrity coverage table: SEM-214 (derived
    operational context views, DRAFT/wave-3, no artifacts) no longer shares an
    `active` row with SEM-215; it now has its own `planned` row. Resolved the
    scheduling inversion for the MUST-priority time-model requirements by
    assigning wave 2 to SEM-227, SEM-228, and SEM-229 in Ground Control, which
    ACTIVE SEM-213 temporal semantics explicitly defer to. (#513)- Corrected the ACES asset-inventory capture guidance so participant-discoverable scenario-target secrets are preserved in source evidence bundles, while operator/out-of-scenario secrets remain withheld or recorded as capture limits. (#516)- Declared `packaging` as a runtime dependency of `aces-sdl`. It was imported by `aces_sdl.module_registry` on the CLI import path but only present transitively, so any `aces` command failed with `ModuleNotFoundError: No module named 'packaging'` in a clean wheel install. (#537)- `aces sdl resolve` now records `local:` imports with a checkout-independent, SDL-base-relative `resolved_source` (POSIX separators) instead of an absolute machine path, so a committed `aces.lock.json` is portable. `aces sdl verify-imports` now passes on any checkout regardless of its absolute path — including CI and other contributors' machines — and fails only when imported content actually changes. Lockfiles generated before this fix contain absolute paths and are treated as stale; re-run `aces sdl resolve` to regenerate them. (#551)- ### Fixed

  - Reduced native TechVault libvirt live-gate helper complexity and documented generated boot-artifact permissions so SonarCloud accepts the native backend path.
  - Kept the native TechVault live CLI on a clean-boot-only public path and moved the generated boot-artifact permission exception into scoped Sonar configuration. (#601)- Made libvirt backend teardown idempotent: a DELETE for a domain or network that is already absent now succeeds as torn down (connection, permission, and ownership failures still fail closed), and a partial CREATE that defines a domain before it fails to start is now rolled back so no orphaned domains, networks, or seed media are left behind. (#604)- ### Fixed

  - Enforced SDL variable declaration-name grammar and embedded placeholder validation consistently across parser, semantic validation, and published schemas, with factored traversal for variable-reference checks. (#655)- Target conformance no longer assumes every backend can realize an arbitrary
  reference scenario. `run_target_conformance` accepts an optional
  `reference_scenario`, so a fixed-topology emulation or bounded simulation
  backend can certify against a scenario it declares it can realize instead of
  being wrongly failed for not realizing a hard-coded `vm` node; the issue #606
  full-realization guard still applies to whichever scenario is selected.
  Temporary bridge superseded by the realizability-envelope design (#667/#668). (#663)- - Restored SonarCloud configuration to the existing KeplerOps ACES SDL project
    while leaving the GitHub repository location under `autarchy-ai/aces`.

## [0.17.0] - 2026-05-10

### Added

- `implementations/python/packages/aces_sdl/semantics/objective_semantics.py` —
  the pure, name-level source of truth for declarative-objective semantics
  (`SEM-207`): actor binding (an authored `agent` xor `entity`), target
  resolution through the targetable named-reference index, success
  interpretation (`mode` over referenced conditions/metrics/evaluations/TLOs/
  goals), the optional window (delegated to `analyze_objective_window`), and the
  acyclic `depends_on` ordering relation. `analyze_objective_semantics` resolves
  those references into a normalized typed IR (`ObjectiveReference` /
  `ObjectiveResourceDependencies` / `ObjectiveSemanticAnalysis`) and reports
  machine-readable issues callers translate into their own envelope. The
  "success and `depends_on` edges order *and* refresh; window edges only
  refresh; actor and target references are normalized but carry no runtime
  dependency role today" fact lives in one place
  (`partition_objective_dependencies` plus the `OBJECTIVE_*_DEPENDENCY_ROLES`
  constants, each gated independently so a future role change to one category
  lands in exactly one place). Derived ordering/refresh names are kind-qualified
  (`condition.<n>`, `metric.<n>`, `objective.<n>`, `workflow.<n>`, …) so
  cross-namespace SDL names cannot collapse. Per ADR-015 it lives with the SDL
  package and has no processor-runtime dependencies; mirrored as a compatibility
  re-export at `aces.core.semantics.objective_semantics`.
- `specs/formal/objectives/declarative-objective-semantics.md` — the formal
  artifact for the declarative-objective semantic boundary (`SEM-207`): canonical
  inputs, the required actor/target/success/window/dependency semantics, the
  cross-cutting gates, the extensibility seam, anti-patterns, and the
  implementation/test mapping.
- `docs/explain/reference/objective-semantics.md` — the implementer-facing
  reference note for `SEM-207` (governed by ADR-016), linked from the reference
  index and the docs toctree.
- A `TestObjectiveSemantics` / `TestObjectiveDependencyPartition` suite in
  `implementations/python/tests/test_semantics_objectives.py` and a
  `TestObjectiveSemanticAgreement` suite in
  `implementations/python/tests/test_fm2_semantics.py` — unit tests for the
  helper plus cross-stage agreement tests (validator and compiler agree on the
  objective reference errors; compiler and planner agree that a condition change
  cascades a refresh through `objective -> depends_on -> objective`).

### Changed

- `aces_sdl.validator` now routes `_verify_objectives` through
  `analyze_objective_semantics` (rendering the machine-readable issue codes back
  onto the existing authoring-error strings via `_OBJECTIVE_ISSUE_RENDERERS`);
  `aces_processor`'s compiler derives `ObjectiveRuntime` ordering/refresh
  dependencies via `partition_objective_dependencies`. Behavior-preserving —
  every authoring error string and compiler diagnostic code is unchanged.
- `docs/explain/reference/shared-semantic-integrity.md` — the `SEM-200` Coverage
  Model row for declarative objectives moves to `active`, covering `authoring,
  validation, instantiation, compilation, planning`, with the new helper, spec,
  and tests as realizing artifacts.
- `specs/formal/objectives/README.md` — the implementation mapping and test
  lists name the new helper, the `_verify_objectives` pass, and
  `partition_objective_dependencies`.
- `SEM-207` ("Declarative Objective Semantics") transitions `DRAFT -> ACTIVE` in
  Ground Control.

### Refactor

- `analyze_objective_semantics` is split into five private resolvers
  (`_analyze_actor_binding`, `_analyze_targets`, `_analyze_success`,
  `_analyze_window`, `_analyze_dependencies`) and the new
  `AssessmentResourceCatalog` / `WindowResourceCatalog` dataclasses bundle the
  nine SDL section maps into two structured inputs, dropping the analyzer's
  signature from 14 parameters to 7 and removing the high cognitive-complexity
  hot spot SonarCloud flagged on the first run. `_analyze_actor_binding` itself
  is decomposed further into `_check_agent` / `_check_agent_actions` /
  `_check_entity` so each helper stays under the cognitive-complexity threshold.
  Behavior-preserving — every authoring error string and compiler diagnostic
  code is unchanged.

## [0.16.0] - 2026-05-10

### Added

- `implementations/python/packages/aces_sdl/semantics/assessment.py` — the
  pure, name-level source of truth for the assessment-pipeline semantics
  (`SEM-206`): the scoring chain
  `condition bindings -> metrics -> evaluations -> TLOs -> goals`. It resolves
  the cross-resource references along the chain into a normalized typed IR
  (`AssessmentReference` / `AssessmentResourceDependencies` /
  `AssessmentPipelineAnalysis`), derives each evaluation's metric-max-score
  total, enforces the "at most one metric per condition" rule and the
  absolute-`min-score`-vs-total rule, and reports machine-readable issues
  callers translate into their own envelope. The "every scoring-chain edge is
  both an ordering edge and a refresh edge" fact lives in one place
  (`ASSESSMENT_DEPENDENCY_ROLES` / `partition_assessment_dependencies`). Per
  ADR-015 it lives with the SDL package and has no processor-runtime
  dependencies; mirrored as a compatibility re-export at
  `aces.core.semantics.assessment`.
- `specs/formal/assessment/` — the formal artifacts for the assessment-pipeline
  semantics (`README.md` scope/implementation mapping; `pipeline-consistency.md`
  reference model, consistency rules, aggregation and dependency/refresh
  semantics, fail-closed cases, composition-ready invariants).
- `docs/explain/reference/assessment-semantics.md` — the architecture-preflight
  guardrails note for `SEM-206` (governed by ADR-016), linked from the
  reference index and the docs toctree.
- `implementations/python/tests/test_semantics_assessment.py` and a
  `TestAssessmentPipelineAgreement` suite in
  `implementations/python/tests/test_fm2_semantics.py` — unit tests for the
  helper plus cross-stage agreement tests (validator and compiler agree on the
  pipeline reference errors; compiler and planner agree that a condition change
  cascades a refresh through `metric -> evaluation -> TLO -> goal`).

### Changed

- `aces_sdl.validator` now routes the metric/evaluation/TLO/goal reference and
  `min-score` checks through `analyze_assessment_pipeline` (the four
  `_verify_metrics` / `_verify_evaluations` / `_verify_tlos` / `_verify_goals`
  passes collapse into one `_verify_assessment_pipeline`); `aces_processor`'s
  compiler derives `MetricRuntime` / `EvaluationRuntime` / `TLORuntime` /
  `GoalRuntime` ordering/refresh dependencies via
  `partition_assessment_dependencies`. Behavior-preserving — every authoring
  error string and compiler diagnostic code is unchanged.
- `docs/explain/reference/shared-semantic-integrity.md` — the `SEM-200`
  Coverage Model row for the assessment construct family moves to `active`,
  covering `authoring, validation, compilation, planning, execution,
  observation`, with the new helper, spec, and tests as realizing artifacts.
- `SEM-206` ("Assessment Semantics") transitions `DRAFT -> ACTIVE` in Ground
  Control.

## [0.15.0] - 2026-05-10

### Added

- ADR-016 ("Semantic Layer Scope and Coverage Model (SEM-200)") under
  `docs/decisions/adrs/`: `SEM-200` is recorded as a system-level umbrella
  requirement that is the *parent* of its ~28 `SEM-2xx` children (the construct
  families) and `DEPENDS_ON` `DSL-100`; a number of `EXP-*` / `AUT-*` / `GOV-*` /
  `ASR-*` / API/runtime requirements `DEPENDS_ON` it as downstream consumers and
  do not gate it. ADR-016 fixes the *model* — the seven canonical lifecycle
  phases (authoring, validation, instantiation, compilation, planning, execution,
  observation), the construct-family concept, the `active` / `partial` /
  `planned` status vocabulary, and `SEM-200`'s definition of done (every
  `SEM-2xx` child `ACTIVE`; no `partial`/`planned` rows in the coverage table;
  cross-stage agreement tests extended construct-wide; the unassigned-wave
  `SEM-2xx` children assigned to a wave). `SEM-200` stays `DRAFT` until then.
- `docs/explain/reference/shared-semantic-integrity.md` (the architecture-preflight
  guardrails note for `SEM-200`) gains the live, ADR-016-governed `## Coverage
  Model` table mapping every semantic construct family to its owning
  requirement(s), realizing artifacts, covered lifecycle phases, and status. The
  table lives in this mutable reference note — not in the immutable ADR — so
  routine `SEM-2xx` implementation PRs can update their construct family's row
  without an ADR amendment; ADR-016 governs it and is linked from it. For
  `planned` rows the table records the owning requirement(s) only; the intended
  scope and wave come from those requirements' Ground Control records, not from a
  duplicated table column. Higher-level capabilities that consume the semantic
  layer (cross-run comparability, federation/standards profiles, …) are tracked
  by their own requirements, not in this table.
- `tools/check_semantic_coverage.py` — a filesystem-only structural gate that
  parses that Coverage Model table and fails if a row is malformed, a status or
  lifecycle-phase token is unrecognised, an owning-requirement token is not
  UID-shaped, an artifact-cell token that looks like a path is missing, escapes
  the repo root, or is not under a supported root, an `active`/`partial` row
  names no lifecycle phase or no existing *non-test* realizing artifact, an
  `active` row names no existing `implementations/python/tests/test_*.py` test, a
  `planned` row claims phases or artifacts, or ADR-016 stops referencing the note
  by path. Row diagnostics report the real source-line number. Failures use
  `tools.policy.common.PolicyFailure`, and the CLI honours `--json` and the
  shared `tools/policy/exceptions.yaml` waiver mechanism, like the other `policy`
  nox-stage entry points. Wired into the `policy` step of the nox verification
  graph (`_run_policy` in `noxfile.py`) for working-tree runs only (skipped on
  the `--staged` pre-commit invocation, since it validates files on disk), added
  to `TARGETED_POLICY_TESTS`, and the new tooling test is exempted in
  `check_requirement_governance.py`'s `REQUIREMENT_CONTEXT_EXEMPT_PATHS`
  alongside the other policy-tooling tests; covered by
  `implementations/python/tests/test_semantic_coverage.py`.

## [0.14.0] - 2026-05-10

### Added

- `MOD-001` ("Codebase Modularity And Layering") requirement in Ground
  Control as the initiative anchor for the modularity work tracked by
  issue #3 (the cycle break + size-cap gate + the 14 file-split child
  PRs). Added to `tools/policy/requirement_order.yaml` as the sole
  requirement of a new `modularity-initiative` phase.
- ADR-015 ("SDL-Processor Layering and Source-File Size Cap") under
  `docs/decisions/adrs/`: SDL is the lower layer, circular imports
  between SDL and processor are forbidden, and non-test source files
  under `implementations/python/packages/` cap at 600 lines with a
  draining allowlist.
- `layering_rules` block in `tools/policy/adr_policy.yaml` and
  `_check_layering` in `tools/policy/repo_policy.py`: rejects any
  `import aces_processor` / `from aces_processor … import …` line in a
  changed `.py` file under `implementations/python/packages/aces_sdl/`.
  New `layering-rule-violation` rule id.
- `oversized_source_files` block in `tools/policy/adr_policy.yaml` and
  `_check_oversized` in `tools/policy/repo_policy.py`: rejects a changed
  non-test `.py` file under `implementations/python/packages/` that
  exceeds 600 lines and isn't in the allowlist. New
  `oversized-source-file` rule id.
- `tools/policy/oversized_allowlist.yaml` listing the 14 source files
  over the cap when ADR-015 landed, and `_ADR015_INITIAL_OVERSIZED_FILES`
  in `tools/policy/repo_policy.py` — a *code constant*, not config —
  holding that same fixed set as the locked reference. `_check_drain`
  (new `oversized-allowlist-locked` rule id) requires the allowlist to be
  a subset of that constant, so entries can be drained (split PRs) but
  not added; pinning the reference in code rather than `adr_policy.yaml`
  stops a single PR from relaxing the rule by editing both lists.
  `_check_allowlist_entries_still_oversized` (new
  `oversized-allowlist-stale-entry` rule id) requires every allowlist
  entry from the initial set to still resolve to a regular file over the
  cap, so a split PR that drops a file below 600 lines but forgets to
  drain its entry is flagged on the next policy run.
- Schema validation for the policy YAML: malformed config surfaces as
  `policy-config-malformed` instead of a traceback — `adr_policy.yaml`
  itself failing to parse or not having a mapping root (loaded through a
  guard before any checker runs), the `layering_rules` /
  `oversized_source_files` blocks having wrong types or empty required
  lists, and an unparseable / non-mapping `oversized_allowlist.yaml`.
  Both ADR-015 blocks are *required* — an absent block is a malformation,
  not an opt-out, so the gates cannot be silently disabled. Path safety
  is enforced at a
  single chokepoint: `evaluate_repo_policy` drops any changed path that
  resolves outside the repository root (absolute, parent-traversal, or a
  planted symlink) *before any checker reads a file*, so the layering
  scan, the size cap, and the pre-existing import-direction and
  compat-wrapper checks all run on an already-validated list. The
  allowlist file path and each allowlist entry the drain check inspects
  are validated the same way. An out-of-tree path surfaces as the new
  `policy-path-unsafe` rule id and the target is never opened.
- `docs/api/sdl-semantics.rst` documenting the moved
  `aces_sdl.semantics.{objectives,workflow}` modules; `docs/index.md`
  toctree updated (ADR list + the new API page).
- Unit tests in `implementations/python/tests/test_repo_policy_tools.py`
  for the layering rule (all four import shapes + the prefix-boundary
  case), the cap (over/under/allowlisted/test-excluded), the drain rule
  (subset of the code constant; config cannot grow the locked set;
  premature drain rejected; legitimate drain passes), the
  stale-allowlist-entry rule (file below cap / missing / replaced by an
  out-of-tree symlink), the required-block and malformed-config paths
  (including a non-mapping/parse-broken `adr_policy.yaml`), the
  unsafe-path chokepoint, and the config-wide checks running on an empty
  changed list (deletion-only PRs).

### Changed

- Moved `aces_processor/semantics/{objectives,workflow}.py` to
  `aces_sdl/semantics/{objectives,workflow}.py`. These are SDL-language
  semantics — objective-window analysis, the workflow step-type contract,
  branch closure, and the (pure, stdlib-only) workflow step-result
  validator — needed by `aces_sdl/validator.py`. The move breaks the
  `aces_sdl ↔ aces_processor` circular import that ran through
  `aces_sdl/validator.py` →
  `aces_processor.semantics.{objectives,workflow}`. The whole module
  contents moved as a unit; `validate_workflow_step_result` stays with
  the rest of `workflow.py` (it is pure and has no import-time coupling
  to `aces_processor`, so moving it does not violate the layering rule
  and keeping it grouped avoids fragmenting `aces.core.semantics.workflow`).
  **Breaking change to the owning-package surface:** the import paths
  `aces_processor.semantics.objectives` and
  `aces_processor.semantics.workflow` no longer exist. Per ADR-009/010
  the *stable* public surface is the `aces.*` namespace, not the owning
  packages, so this follows the documented compatibility model: code
  that imported the owning-package paths directly must move to
  `aces_sdl.semantics.*`, and consumers of the stable API are
  unaffected — `aces.core.semantics.{objectives,workflow}` keep working,
  retargeted to re-export from `aces_sdl.semantics.*`.
- `aces_processor/semantics/planner.py` is **not** moved — it is
  processor-runtime reconciliation logic over a processor artifact
  (resource-action reconciliation between compiled resources and runtime
  snapshots, dependency graphs over compiled-resource addresses),
  consumed only by `aces_processor`, and stays there. After this PR
  `aces_processor.semantics` contains only `planner`.
- Updated import sites in `aces_processor/{compiler,manager,models}.py`
  and `aces_sdl/validator.py` to reach the moved modules via
  `aces_sdl.semantics.{objectives,workflow}`. `aces_processor/manager.py`
  keeps `.semantics.planner` for the planner helpers.
- Retargeted the `aces.core.semantics.{objectives,workflow}`
  compatibility wrappers to `aces_sdl.semantics.*`.
  `aces.core.semantics.planner` is unchanged. Tests that import via the
  `aces.core.semantics.*` namespace work without modification.
- `docs/api/sdl-semantics.rst` (new) documents the moved
  `aces_sdl.semantics.{objectives,workflow}` modules;
  `docs/api/processor-semantics.rst` is rescoped to
  `aces_processor.semantics.planner` only.

## [0.13.0] - 2026-05-09

### Added

- `AUT-807` ("Machine-Readable Guidance And Discovery Surfaces") MCP
  server at `implementations/python/packages/aces_mcp/`, exposing 14
  tools for SDL understanding, authoring, and inspection to any agent
  speaking the Model Context Protocol. Tools split across three
  modules:
  - `aces_mcp.tools.reference` — `sdl_overview`,
    `sdl_section_reference`, `sdl_get_example`, `sdl_parser_reference`,
    `sdl_validation_reference`.
  - `aces_mcp.tools.authoring` — `sdl_validate`, `sdl_scaffold`,
    `sdl_instantiate`, `sdl_compose`, `sdl_minimal_example`.
  - `aces_mcp.tools.inspection` — `sdl_list_elements`,
    `sdl_get_element`, `sdl_check_references`, `sdl_diagram`.
  Recreates PR #2 on top of the post-realignment dev branch with all
  imports retargeted from `aces.core.sdl.*` to the canonical
  `aces_sdl.*` packages, plus the original entry-point bug fixed
  (`aces-mcp = "aces_mcp.server:main"` rather than the broken
  `aces.mcp.__main__:server.run` form that re-imported the module
  during entry-point resolution and triggered a double-run).
- `mcp>=1.0.0` runtime dependency in
  `implementations/python/pyproject.toml`. The aces_mcp package and
  test file are added to the `documentation-surfaces` policy phase
  ownership.
- 45 unit tests covering all 14 tools, all three scaffold templates
  (verified to produce valid SDL), and the three example scenarios.

### Changed

- `AUT-807` and `AUT-809` transitioned from DRAFT to ACTIVE in Ground
  Control. The MCP server materially implements AUT-807 (machine-
  readable discovery) and contributes to AUT-809 (semantic parity
  across agent / CLI / docs surfaces). Traceability IMPLEMENTS / TESTS
  links recorded against AUT-807 for every aces_mcp file and the test
  file.

## [0.12.0] - 2026-05-09

### Added

- ADR-014 ("nox as the Canonical Verification Graph") capturing the
  rationale for nox-as-canonical-gate that was introduced in 0.10.0
  without an accompanying ADR. The decision codifies what the
  repository already does: one verification graph in `noxfile.py`, with
  pre-commit, pre-push, and CI all resolving through the same `_run_*`
  helpers, and `.ground-control.yaml` exposing the same commands to
  ecosystem agents.
- `.ground-control.yaml` now declares `workflow.format_command`
  (`nox -s hygiene`) and tightens `workflow.lint_command` from the
  full `verify` graph to the dedicated `lint` session. Optional
  `docs.adr_dir`, `example_paths.{source,test}`, and
  `requirements.uid_examples` blocks are populated so the
  ground-control context the `/implement` skill consumes points at
  this repository's actual paths and UID style instead of generic
  fallbacks.

## [0.11.0] - 2026-05-09

### Added

- `AUT-805` ("Canonical Documentation, Glossary, And Reference Material")
  Sphinx documentation site under `docs/` with `furo` theme, MyST markdown
  support, copy-button, and autodoc against the canonical packages
  (`aces_cli`, `aces_sdl`, `aces_processor`, `aces_processor.semantics`).
  Recreates the original PR #1 work on top of the post-realignment layout
  per ADR-009/010. API reference pages target the canonical `aces_*`
  packages rather than the `aces.*` compatibility shims.
- `nox -s docs` session that runs `sphinx-build`, joining the canonical
  verification graph alongside hygiene, policy, lint, contracts, and
  tests. Local hooks and CI invoke the same session.
- `docs` extras in `implementations/python/pyproject.toml` covering
  `sphinx`, `furo`, `myst-parser`, `sphinx-copybutton`, and
  `sphinx-autobuild`.
- New `documentation-surfaces` phase in
  `tools/policy/requirement_order.yaml` covering `AUT-805`, `AUT-807`,
  `AUT-809`, and `ASR-516`. Phase is blocked on `gov-concept-authority`
  (canonical concepts must exist before they can be documented) and
  owns `docs/`, `implementations/python/pyproject.toml`, and
  `implementations/python/uv.lock`.

## [0.10.0] - 2026-04-11

### Added

- `RUN-311` ("Participant Episode Lifecycle And Reset") participant
  episode contract surface: `ParticipantEpisodeStatus`,
  `ParticipantEpisodeTerminalReason`, `ParticipantEpisodeControlAction`,
  `ParticipantEpisodeHistoryEventType`,
  `ParticipantEpisodeExecutionState`, and
  `ParticipantEpisodeHistoryEvent` in
  `implementations/python/packages/aces_processor/models.py`, modelling
  current lifecycle state, terminal reasons, and control actions as
  three distinct categories per ADR-013.
- Closed-world contract models `ParticipantEpisodeStateModel` and
  `ParticipantEpisodeHistoryEventModel` plus matching
  `participant-episode-state-envelope-v1` /
  `participant-episode-history-event-stream-v1` entries in
  `schema_bundle()`, with the new `participant-episode-state/v1`
  schema-version constant in
  `implementations/python/packages/aces_contracts/versions.py`.
- Generated JSON Schemas in `contracts/schemas/control-plane/` and
  minimal valid/invalid fixture pairs in
  `contracts/fixtures/control-plane/`.
- ADR-013 ("Participant Episode Lifecycle Boundaries") in
  `docs/decisions/adrs/` defining the contract-surface boundary
  discipline that drives this work.
- Contract-surface coverage in
  `implementations/python/tests/test_run_311_participant_episode_lifecycle.py`
  exercising every clause of the requirement (initialization, reset,
  completion, timeout, truncation, interruption, restart) at the
  ``ParticipantEpisodeExecutionState`` /
  ``ParticipantEpisodeHistoryEvent`` boundary, plus the per-clause
  invariants on stable participant identity across resets/restarts.
  End-to-end coverage of the runtime + HTTP control surfaces lives
  alongside the participant runtime added under finding 1 below
  (``test_runtime_control_plane.py::TestParticipantEpisodeControlPlane``
  and
  ``test_runtime_control_plane_api.py::TestParticipantEpisodeHttpRoutes``).
- `RuntimeSnapshot` and `RuntimeSnapshotEnvelopeModel` now carry
  `participant_episode_results` and `participant_episode_history`
  alongside the existing `orchestration_*` and `evaluation_*` surfaces.
  Both are keyed by the stable `participant_address`. Matching
  serialization in `aces_processor/control_plane_api.py::_snapshot_model`,
  `aces_processor/control_plane_store.py::_snapshot_payload`, and
  `aces_conformance/conformance.py` routes the new data through
  `/snapshot` responses and durable snapshot state instead of forcing
  it into `RuntimeSnapshot.metadata`.
- Stream-level invariants on `ParticipantEpisodeHistoryEvent`:
  `episode_initialized` must carry `sequence_number=0`, and
  `episode_reset` / `episode_restarted` must carry `sequence_number>0`,
  matching the `ParticipantEpisodeExecutionState` invariants so a valid
  history stream can always be reconstructed into a valid state chain.
- Manifest-authority registration: the new
  `participant-episode-state-envelope-v1` and
  `participant-episode-history-event-stream-v1` contract ids are now
  members of `BACKEND_SUPPORTED_CONTRACT_IDS` and
  `PROCESSOR_SUPPORTED_CONTRACT_IDS`, added to the conformance
  `FULL_REMOTE_CONTROL_PLANE` profile requirements, and wired into
  `aces_conformance.conformance._validate_payload` and
  `_semantic_diagnostics`. The reference backend stub fixture at
  `contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json`
  is updated to match the widened authority list.
- `_live_target_cases()` live conformance probe now serializes
  `participant_episode_results` / `participant_episode_history` from
  the live ``RuntimeControlPlane.snapshot``. Note: the original drop
  of this entry overstated coverage by implying serialization alone
  rejected malformed data; the *active* lifecycle drive that actually
  produces and validates participant data lives under finding 4 below.
- Shared snapshot invariant iterator
  `aces_processor.models.iter_participant_episode_snapshot_violations`,
  consumed by both the runtime-manager apply path
  (`_participant_episode_contract_diagnostics`) and the conformance
  semantic-check path (`_participant_episode_snapshot_diagnostics`) so
  both callers use one source of truth for per-entry validation and
  stream-level consistency (outer-key/inner-address match, monotonic
  `sequence_number`, stable `episode_id` per sequence, and `RESET` /
  `RESTARTED` gating on cross-sequence transitions).
- Ground Control IMPLEMENTS and TESTS traceability links from `RUN-311`
  to the new processor models, contract models, schema-version constant,
  ADR-013, the conformance wiring, and the lifecycle test.

### Fixed

- Production-readiness review finding 5: tighten the original 0.10.0
  release notes that overstated RUN-311 completeness relative to the
  contract-only code that initially landed. The
  ``test_run_311_participant_episode_lifecycle.py`` entry is now
  scoped to "contract-surface coverage" with an explicit pointer to
  the runtime/HTTP test classes added under finding 1, and the
  ``_live_target_cases`` entry now distinguishes the original
  serialization-only behavior from the active lifecycle drive added
  under finding 4. Findings 1-4 below independently document the
  runtime, conformance, and validation gaps the original wording
  understated; this entry exists so the historical Added section
  describes only what shipped at each point in time.
- Production-readiness review finding 4: ``aces_conformance.conformance``
  now actively drives a full participant episode lifecycle whenever the
  target advertises a participant runtime. ``_live_target_cases`` calls
  the new ``_drive_participant_episode_probe`` which submits
  ``initialize`` / ``reset`` / ``terminate`` / ``restart`` through the
  control plane, then adds a ``participant-snapshot-consistent``
  conformance case that fails when ``participant_episode_results`` or
  ``participant_episode_history`` is empty after the lifecycle, or when
  the resulting snapshot violates ``iter_participant_episode_snapshot_violations``.
  Backends that register a participant runtime but never publish
  state/history through the snapshot now fail conformance instead of
  silently certifying clean. Regression coverage in
  ``test_live_probe_catches_participant_runtime_that_does_not_populate_snapshot``.
- Production-readiness review finding 3: ``profile_for_manifest`` now
  promotes a manifest that declares orchestrator, evaluator, AND
  participant runtime to ``BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE``
  so the default ``run_target_conformance`` path automatically validates
  the live target against the participant-episode contract family
  (RUN-311) without callers having to override the profile.
  ``_capability_gaps`` now requires a ``participant_runtime`` component
  for that profile, and ``test_runtime_conformance`` covers both the
  promotion path and the orchestration-evaluation fallback for backends
  that omit the participant runtime block.
- Production-readiness review finding 1: RUN-311 now ships an actual
  runtime capability, not just contracts and validators. New
  ``ParticipantRuntime`` backend protocol on
  ``aces_backend_protocols/protocols.py`` defines ``initialize`` /
  ``reset`` / ``restart`` / ``terminate`` plus the standard
  ``status`` / ``results`` / ``history`` observation methods. New
  ``ParticipantRuntimeCapabilities`` capability block on
  ``BackendCapabilitySet`` plus a ``has_participant_runtime`` property
  on ``BackendManifest`` let backends advertise the surface and let
  ``RuntimeTarget`` shape validation reject targets whose component
  presence does not match the manifest. ``RuntimeControlPlane``
  exposes ``initialize_participant_episode``,
  ``reset_participant_episode``, ``restart_participant_episode``, and
  ``terminate_participant_episode``, each routing through the existing
  idempotency / persistence / audit pipeline and emitting an
  ``OperationReceipt`` / ``OperationStatus`` under a new
  ``RuntimeDomain.PARTICIPANT`` domain. ``control_plane_api.py``
  publishes the four matching POST routes under
  ``/participants/{participant_address}/episodes/*`` with closed-world
  request bodies. The reference stub backend gains a new
  ``StubParticipantRuntime`` that implements every transition with
  RUN-311-correct sequence/episode_id/previous_episode_id semantics
  and updates the snapshot in lockstep with the published contract.
  Tests cover the in-process control plane lifecycle, the HTTP API,
  the rejection paths (no participant runtime, already terminated,
  duplicate initialize, etc.), idempotency replay, and a full
  end-to-end ``initialize → reset → terminate → restart`` chain that
  must satisfy ``iter_participant_episode_snapshot_violations``.
- `iter_participant_episode_snapshot_violations` now cross-checks each
  ``participant_episode_results`` entry against the head of the
  corresponding ``participant_episode_history`` chain. A stale result
  that still points at an earlier episode than the history shows — the
  specific scenario raised as production-readiness review finding 2 —
  fails validation with ``does not match head of history chain``.
  Identity (``episode_id`` + ``sequence_number``), status category, and
  ``terminal_reason`` must all agree with the last valid history event
  for the same participant. Apply-path and conformance semantic-check
  paths both pick this up automatically via the shared helper.
- `iter_participant_episode_snapshot_violations` no longer produces
  cascading duplicate violations when a stream-level rule fires. Both
  the sequence-transition gate and the per-sequence ``episode_id``
  stability check now advance stream state after every yielded
  violation except strict backward movement, so an ungated sequence
  transition reports one error per transition and an ``episode_id``
  mismatch reports each distinct transition (e.g. ``A -> B`` then
  ``B -> C``) instead of repeating the same comparison against the
  first-observed id.

### Changed

- `tools/policy/requirement_order.yaml`: `RUN-311` added to the
  `runtime-core` phase (it is the next runtime/control-plane sibling
  after `RUN-300`). Phase ownership widened to cover
  `docs/decisions/adrs`, `contracts/schemas/snapshots`,
  `contracts/schemas/backend-manifest`,
  `contracts/schemas/processor-manifest`,
  `contracts/fixtures/backend-manifest`,
  `contracts/fixtures/processor-manifest`, and
  `implementations/python/packages/aces_conformance` so the ADR and the
  conformance/schema wiring clear `check_requirement_governance.py`.
- `aces_conformance.conformance._validate_event_stream` extracted from
  the repeated history-stream validation blocks so workflow, evaluation,
  and participant-episode history streams share one helper.

## [0.9.0] - 2026-04-11

### Added

- RUN-300 lifecycle integrity test
  (`implementations/python/tests/test_run_300_lifecycle.py`) that threads
  a parameterized scenario through instantiation, compilation, planning,
  execution, and live observation, asserting substituted parameter values
  survive unchanged through instantiation, compilation, planning, and
  apply; canonical addresses survive unchanged across all five stages;
  and provenance drift (a stale plan base snapshot) is rejected rather
  than silently reconciled.
- Ground Control IMPLEMENTS and TESTS traceability links from RUN-300
  (Processing Model and Lifecycle) to the processor/compiler/planner/
  manager/control-plane stack and its per-stage tests.

## [0.8.0] - 2026-04-11

### Added

- `.ground-control.yaml` declaring workflow commands (nox verify),
  sonarcloud key (`autarchy-ai_aces` in `autarchy-ai` org), and
  plan rules reference.
- `.gc/plan-rules.md` containing the ACES SDL hard rules and required
  checks (previously in AGENTS.md prose), rewritten as "plans MUST..."
  bullets for the `/implement` skill plan phase.

### Changed

- `AGENTS.md` Ground Control Context block replaced with a pointer to
  `.ground-control.yaml`. Hard rules and required checks now live in
  `.gc/plan-rules.md`.
- `.mcp.json` `GH_REPO` corrected from `KeplerOps/Ground-Control` to
  `autarchy-ai/aces`.

## [0.7.0] - 2026-04-11

### Changed

- API-413 no longer publishes, generates, or tests a `backend-manifest-v1`
  compatibility surface. The backend manifest authority is now `v2` only.
- Backend `v2` manifests now use a backend-specific compatibility surface that
  declares compatible processors only, and they validate declared supported
  contract ids against the shared backend manifest authority set on both the
  contract-model path and the runtime dataclass path.
- The reference backend stub and backend conformance path now consume the
  shared backend manifest authority directly, reducing drift between authority
  sets, emitted manifests, fixtures, and conformance validation.

### Fixed

- API-413 backend conformance now fails when a backend under-declares the
  contract ids required by its inferred runtime capability profile, instead of
  trusting capability shape alone.
- Published schema checks now reject stale extra schema files that are no
  longer generated from the live contract bundle, closing the hole where a dead
  `backend-manifest-v1` file could silently creep back into `contracts/schemas`.
- Backend manifest regression tests now keep valid `concept_bindings` in place
  and assert the intended failure causes for empty compatibility,
  under-specified realization support, and hollow capability blocks.

## [0.6.0] - 2026-04-11

### Added

- Canonical `nox` verification graph for repo policy, lint, contract/schema
  validation, tests, and fuzz checks, with local hooks and CI calling the same
  sessions instead of maintaining separate command lists.
- Standard-tooling enforcement for repo structure and JSON contracts through
  Conftest/OPA and `check-jsonschema`, plus repo-local bootstrap helpers for
  those tools so the policy and contract gates fail locally before CI.
- Repo-local `gitleaks` bootstrap and `nox` hygiene session covering generic
  file/security checks inside the same canonical verification graph as lint,
  policy, contracts, and tests.

### Changed
- API-412 no longer publishes, generates, or tests a `processor-manifest-v1`
  compatibility surface. The processor manifest authority is now `v2` only.
- Local pre-commit and pre-push hooks now use the canonical verification graph,
  with commit-time policy/lint/contract/test gating and push-time full verify
  plus fuzz coverage to match CI semantics.
- `nox` now emits explicit start/pass/fail/skip status for each check stage and
  each session summary, while `.pre-commit-config.yaml` is now a thin trigger
  layer instead of a second source of substantive check logic.

### Fixed

- Fix `_run_changed_lint` in noxfile crashing on repo-relative paths passed to
  `Path.relative_to()` with an absolute `PROJECT_ROOT`.

## [0.5.0] - 2026-04-10

### Changed

- API-412 processor manifests now keep `v2` focused on processor identity,
  contract support, backend compatibility, processor capabilities, and concept
  bindings. `realization_support` is no longer part of the processor manifest
  contract surface, and processor `compatibility` is now backend-only instead
  of the generic apparatus compatibility shape. Declared SDL versions and
  supported contract versions are now validated against the repo-published
  processor/runtime contract ids instead of remaining open string fields.

## [0.4.0] - 2026-04-10

### Added

- GOV-922 controlled-vocabulary catalog, schema, fixtures, and validation
  helpers for portable enumerations and governed-extension vocabularies.

### Changed

- Backend capability declarations now validate governed vocabulary values on
  both the contract-model path and the runtime dataclass path.

## [0.3.1] - 2026-04-10

### Fixed

- CI workflow now triggers on pull requests targeting `dev` branch, not just `main`.
- Rename `UID` variable to `REQ_UID` in CI policy job to avoid collision with
  the readonly shell builtin.
- Add `fetch-depth: 0` to policy job checkout so the PR base SHA is available
  for `git diff`.
- Pass branch name via `env:` in CI UID-extraction step instead of relying on
  shell variable expansion of `GITHUB_HEAD_REF`.
- `current_branch()` in `check_requirement_governance.py` now falls back to
  `GITHUB_HEAD_REF` when `git branch --show-current` returns empty (detached
  HEAD in CI PR checkouts).
- Requirement governance check now warns and exits 0 when Ground Control is
  unreachable, instead of failing the build.

## [0.3.0] - 2026-04-05

### Added

- Cross-artifact concept binding for v2 apparatus manifests (GOV-918).
  Backend and processor manifests now require a `concept_bindings` section
  that binds vocabulary fields to canonical concept families from the
  concept-authority catalog.
- Repo-owned ADR enforcement tooling under `tools/policy/`, including
  repo-boundary checks, requirement-order gating, exception handling, and a
  unified verification entrypoint.
- Hard policy integration for local agents and automation through
  pre-commit, GitHub Actions, Claude hooks, `AGENTS.md`, and repo-local
  Codex instructions.
- Targeted policy unit tests covering generated-schema edits, compatibility
  boundaries, requirement ordering, path ownership, and traceability failures.
- `ConceptBindingEntryModel` Pydantic contract with pattern-validated
  `scope` and `family` fields.
- `ConceptFamilyId` pattern-constrained type for concept family identifiers.
- `ConceptBinding` frozen dataclass for runtime concept binding declarations.
- Invalid fixtures for missing, duplicate, and malformed concept bindings.
- Contract-level validation ensuring `concept_bindings` resolve to the
  authoritative concept-families-v1 catalog and to governed manifest
  vocabulary surfaces.
- GOV-919 native extension discipline metadata in the concept-family catalog,
  including extension scope, relation rules, and non-ambiguity constraints.
- Invalid fixtures covering native concept families that omit extension
  discipline fields.
- GOV-920 semantic profile contract, schema, fixtures, and the initial
  `reference-stack-v1` shared semantic profile.
- GOV-921 shared reference model catalog, schema, fixtures, and initial
  recurrent SDL reference models for nodes, accounts, relationships,
  conditions, events, and content.

### Changed

- `BackendManifestV2Model` and `ProcessorManifestV2Model` now require
  `concept_bindings` with at least one entry.
- `BackendManifest` and `ProcessorManifest` frozen dataclasses now require
  `concept_bindings` tuple.
- Backend and processor manifest emission functions emit concept bindings.
- Updated all v2 manifest fixtures with concept binding declarations.
- Updated all v2 invalid fixtures to include concept bindings for single-concern testing.
- Regenerated backend-manifest-v2 and processor-manifest-v2 JSON Schemas.
- `ConceptFamilyDefinitionModel` and the `concept-families-v1` schema now
  reject native families that do not declare GOV-919 extension discipline.
- Documented and validated shared semantic assumptions for authoring, exchange,
  processing, and execution through the new semantic profile surface.
- Documented and validated shared reusable structure anchors for recurrent
  federation-relevant objects through the new reference-model catalog surface.

## [0.2.0] - 2026-04-04

### Added

- Processor manifest declaration surface (`ProcessorFeature` enum,
  `ProcessorManifest` frozen dataclass, `ProcessorManifestModel` Pydantic
  contract) for declaring processor identity, supported language and contract
  versions, processing features, backend compatibility, and constraints
  (API-412).
- Reference processor manifest helpers and `aces processor manifest` CLI output
  for emitting the repo-owned processor declaration.
- JSON Schema `processor-manifest-v1` published to
  `contracts/schemas/processor-manifest/`.
- Valid and invalid processor manifest fixtures in
  `contracts/fixtures/processor-manifest/`.
- Schema generation routing for processor manifest in
  `tools/generate_contract_schemas.py`.
- Pre-commit hooks with ruff (lint + format), gitleaks (secrets), trailing
  whitespace, YAML/JSON checks, and pytest gate.
- GitHub Actions CI workflow with lint, test (coverage), fuzz, contract schema
  drift detection, and SonarCloud analysis.
- SonarCloud project configuration (`sonar-project.properties`).
- GitHub PR template and issue templates (bug report, feature request).
- Ruff linter and formatter configuration in `pyproject.toml`.

## [0.1.0] - 2026-04-03

### Added

- Initial ACES SDL ecosystem extraction from APTL with SDL authoring layer,
  processor layer, backend protocols, conformance infrastructure, and CLI.

[0.6.0]: https://github.com/autarchy-ai/aces/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/autarchy-ai/aces/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/autarchy-ai/aces/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/autarchy-ai/aces/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/autarchy-ai/aces/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/autarchy-ai/aces/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/autarchy-ai/aces/releases/tag/v0.1.0
