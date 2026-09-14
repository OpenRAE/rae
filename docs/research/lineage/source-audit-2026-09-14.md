# SDL lineage immutable-source audit — 2026-09-14

This audit binds the current v2 ledger to immutable external source identities. It supersedes review-date-only identities for the listed sources; the original dated audit remains historical evidence. These are bounded conceptual references, not copied implementation code or claims of runtime compatibility.

Git revisions below were resolved through the official repository commit and contents APIs. The newest retained file revision at or before 2026-07-27 was read and checked for the stated concern. The DRA document uses the last revision before its path moved. SHA-256 values identify the exact upstream file bytes inspected; CI uses the ledger and this audit offline.

## kubernetes-resource-quota-2026

[Kubernetes Resource Quotas](https://github.com/kubernetes/website/blob/e3addf54d95cd6bfbeffc5a84e7b1bda2a21dc5a/content/en/docs/concepts/policy/resource-quotas.md)

Revision: `e3addf54d95cd6bfbeffc5a84e7b1bda2a21dc5a` (2025-11-28T20:55:57Z).
Source file SHA-256: `ff097eaebc0b5155cc48c627563f297ca624348115d0612a32942e5502203069`.

Namespace resource quotas bound aggregate resource consumption.

## kubernetes-api-priority-fairness-2026

[Kubernetes API Priority and Fairness](https://github.com/kubernetes/website/blob/03c191bcc446f9c15a9e68d6cd1154b53bde4291/content/en/docs/concepts/cluster-administration/flow-control.md)

Revision: `03c191bcc446f9c15a9e68d6cd1154b53bde4291` (2026-04-13T16:15:00Z).
Source file SHA-256: `e7577bbfd75d6cb77cc5b3877534d5ee21ab05bffc31d01b6413958448ec6e39`.

API request classification, concurrency allocation, and queuing provide the scheduling analogue.

## kubernetes-dynamic-resource-allocation-2026

[Kubernetes Dynamic Resource Allocation](https://github.com/kubernetes/website/blob/c37d57216103cd3473e82dc7b481bf5b34a1a197/content/en/docs/concepts/scheduling-eviction/dynamic-resource-allocation.md)

Revision: `c37d57216103cd3473e82dc7b481bf5b34a1a197` (2026-05-13T20:32:47Z).
Source file SHA-256: `1fb9ffeb21b02771048ce9ab39fee3093964e74415291a1e35dc75bbc2d13af6`.

Resource claims and device allocation separate requested resources from their selected realization.

## kueue-cluster-queue-2026

[Kueue Cluster Queue](https://github.com/kubernetes-sigs/kueue/blob/e2004ca27b7525308157862333fe64e4d65c114d/site/content/en/docs/concepts/cluster_queue.md)

Revision: `e2004ca27b7525308157862333fe64e4d65c114d` (2026-05-25T10:13:16Z).
Source file SHA-256: `7b35c9f7e8caee0815ca506f463975a09202412422c03c1f63dd91224510b346`.

ClusterQueue governs resource flavors, quotas, and fair sharing.

## oci-linux-container-configuration-2026

[OCI Linux Container Configuration](https://github.com/opencontainers/runtime-spec/blob/09ec668274d512a4235012f43bf9538212cf6a20/config-linux.md)

Revision: `09ec668274d512a4235012f43bf9538212cf6a20` (2025-10-14T23:28:38Z).
Source file SHA-256: `0b9bdad8c8b5ff0ef3e99ff4452c874d9d78a4af347dd145d2b6087e67ca1395`.

Linux namespaces and cgroup resource limits provide isolation and resource-control examples.

## opentelemetry-metrics-semconv-2026

[OpenTelemetry Metrics Semantic Conventions](https://github.com/open-telemetry/semantic-conventions/blob/eb614277f0c401bcffd4169f9a148b995b8c3f87/docs/general/metrics.md)

Revision: `eb614277f0c401bcffd4169f9a148b995b8c3f87` (2026-07-10T15:31:09Z).
Source file SHA-256: `6e6feabd66481bdbbfc59a3b6d7ebdc142752cddf1e225391f72c568002a19bd`.

General metric conventions define instrument and attribute interpretation.

## opentelemetry-genai-metrics-2026

[OpenTelemetry Generative AI Metrics](https://github.com/open-telemetry/semantic-conventions/blob/c9e48b1d1af565454b73b9e14f0841bca4670ada/docs/gen-ai/gen-ai-metrics.md)

Revision: `c9e48b1d1af565454b73b9e14f0841bca4670ada` (2026-05-05T16:10:01Z).
Source file SHA-256: `811e0c5cc3c0c3d65dfda87b7cacf7212c296654c40b00b6e857bae329d7e56a`.

Generative-AI metrics define usage and operation measurements.

## ros2-clock-time-2018

[ROS 2 Clock and Time](https://github.com/ros2/design/blob/12f61b14698b80170824c699c70608d9ded3a6d7/articles/130_ros_time.md)

Revision: `12f61b14698b80170824c699c70608d9ded3a6d7` (2021-10-01T13:24:30Z).
Source file SHA-256: `90c5ba7f4e1296ce59182d1fd15374044ef06d7862fa3e363de8f62a0cc4c6db`.

Clock abstractions distinguish system, steady, and simulated time.

## nsa-cross-domain-2026

Official source: [National Cross Domain Strategy and Management Office](https://www.nsa.gov/Cybersecurity/Partnership/National-Cross-Domain-Strategy-Management-Office/).

Retained [body-text capture](captures/nsa-cross-domain-2026-09-14.txt), SHA-256 `f2604114fbe6226183d041ce79b28b989c7adccab5ceb2bd50048c89c86fb1e6`.

The browser text extraction was available; direct HTML retrieval returned HTTP 403. The capture therefore preserves the extracted title and substantive body, with paragraph and heading breaks, rather than claiming a raw HTTP response. Navigation, contact details, and Intelink addresses are excluded. The page is a U.S. federal agency work. The retained text supports the controlled-interface and cross-domain guidance concern; it provides no certification, approval, or imported security authority.
