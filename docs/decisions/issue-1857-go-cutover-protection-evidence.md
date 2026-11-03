# Go branch admission API evidence

Captured from the existing repository through authenticated `gh api` reads.
No settings were changed during this capture. No merge was attempted.

## Independent sources

- [Ruleset and bypass actors](https://api.github.com/repos/OpenRAE/rae/rulesets/26422222)
- [Effective branch rules](https://api.github.com/repos/OpenRAE/rae/rules/branches/go-cutover)
- [Legacy protection](https://api.github.com/repos/OpenRAE/rae/branches/go-cutover/protection)
- [Repository settings](https://api.github.com/repos/OpenRAE/rae)
- [Live PR state](https://api.github.com/repos/OpenRAE/rae/pulls/1879)
- [Head check runs](https://api.github.com/repos/OpenRAE/rae/commits/9856498860d5e38fac785e924c691f91f0a039f9/check-runs)

The REST value `mergeable_state: blocked` matches the earlier GraphQL `BLOCKED` state.
Required checks were pending on the same head. The PR was mergeable and not a draft.
No reviews were required. No bypass actor existed.
The check links identify each workflow run and job.
These selected native response fields provide settings and behavior evidence.

## Native response fields

```json
{
  "observed_at": "2026-11-03T04:01:01.173719+00:00",
  "ruleset": {
    "id": 26422222,
    "enforcement": "active",
    "conditions": {
      "ref_name": {
        "exclude": [],
        "include": [
          "refs/heads/go-cutover"
        ]
      }
    },
    "rules": [
      {
        "type": "pull_request",
        "parameters": {
          "required_approving_review_count": 0,
          "dismiss_stale_reviews_on_push": false,
          "required_reviewers": [],
          "require_code_owner_review": false,
          "dismissal_restriction": {
            "enabled": false,
            "allowed_actors": []
          },
          "require_last_push_approval": false,
          "required_review_thread_resolution": false,
          "require_extra_approval_for_unattributed_changes": true,
          "allowed_merge_methods": [
            "squash"
          ]
        }
      },
      {
        "type": "required_status_checks",
        "parameters": {
          "strict_required_status_checks_policy": false,
          "do_not_enforce_on_create": false,
          "required_status_checks": [
            {
              "context": "verify",
              "integration_id": 15368
            },
            {
              "context": "sonar",
              "integration_id": 15368
            },
            {
              "context": "fuzz",
              "integration_id": 15368
            },
            {
              "context": "supply-chain",
              "integration_id": 15368
            },
            {
              "context": "CPython 3.14 compatibility",
              "integration_id": 15368
            },
            {
              "context": "CodeQL",
              "integration_id": 57789
            },
            {
              "context": "Analyze (actions)",
              "integration_id": 15368
            },
            {
              "context": "Analyze (python)",
              "integration_id": 15368
            },
            {
              "context": "Analyze (javascript-typescript)",
              "integration_id": 15368
            },
            {
              "context": "GitGuardian Security Checks",
              "integration_id": 46505
            },
            {
              "context": "title-guard",
              "integration_id": 15368
            },
            {
              "context": "body-guard",
              "integration_id": 15368
            }
          ]
        }
      },
      {
        "type": "non_fast_forward"
      },
      {
        "type": "deletion"
      }
    ],
    "bypass_actors": [],
    "current_user_can_bypass": "never"
  },
  "effective_rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "dismissal_restriction": {
          "enabled": false,
          "allowed_actors": []
        },
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "require_extra_approval_for_unattributed_changes": true,
        "allowed_merge_methods": [
          "squash"
        ]
      },
      "ruleset_source_type": "Repository",
      "ruleset_source": "OpenRAE/rae",
      "ruleset_id": 26422222
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {
            "context": "verify",
            "integration_id": 15368
          },
          {
            "context": "sonar",
            "integration_id": 15368
          },
          {
            "context": "fuzz",
            "integration_id": 15368
          },
          {
            "context": "supply-chain",
            "integration_id": 15368
          },
          {
            "context": "CPython 3.14 compatibility",
            "integration_id": 15368
          },
          {
            "context": "CodeQL",
            "integration_id": 57789
          },
          {
            "context": "Analyze (actions)",
            "integration_id": 15368
          },
          {
            "context": "Analyze (python)",
            "integration_id": 15368
          },
          {
            "context": "Analyze (javascript-typescript)",
            "integration_id": 15368
          },
          {
            "context": "GitGuardian Security Checks",
            "integration_id": 46505
          },
          {
            "context": "title-guard",
            "integration_id": 15368
          },
          {
            "context": "body-guard",
            "integration_id": 15368
          }
        ]
      },
      "ruleset_source_type": "Repository",
      "ruleset_source": "OpenRAE/rae",
      "ruleset_id": 26422222
    },
    {
      "type": "non_fast_forward",
      "ruleset_source_type": "Repository",
      "ruleset_source": "OpenRAE/rae",
      "ruleset_id": 26422222
    },
    {
      "type": "deletion",
      "ruleset_source_type": "Repository",
      "ruleset_source": "OpenRAE/rae",
      "ruleset_id": 26422222
    }
  ],
  "legacy_protection": {
    "enforce_admins": {
      "url": "https://api.github.com/repos/OpenRAE/rae/branches/go-cutover/protection/enforce_admins",
      "enabled": true
    },
    "allow_force_pushes": {
      "enabled": false
    },
    "allow_deletions": {
      "enabled": false
    }
  },
  "allow_auto_merge": false,
  "pull_request": {
    "number": 1879,
    "html_url": "https://github.com/OpenRAE/rae/pull/1879",
    "draft": false,
    "mergeable": true,
    "mergeable_state": "blocked",
    "auto_merge": null
  },
  "head_sha": "9856498860d5e38fac785e924c691f91f0a039f9",
  "base": "go-cutover",
  "checks": [
    {
      "name": "canonical / proof",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078864"
    },
    {
      "name": "canonical / parity-inputs (3)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078766"
    },
    {
      "name": "canonical / parity-inputs (4)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078736"
    },
    {
      "name": "canonical / parity-inputs (0)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078733"
    },
    {
      "name": "canonical / parity-inputs (1)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078686"
    },
    {
      "name": "canonical / parity-inputs (7)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078646"
    },
    {
      "name": "canonical / integration",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078635"
    },
    {
      "name": "canonical / parity-inputs (5)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078618"
    },
    {
      "name": "canonical / parity-inputs (6)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078608"
    },
    {
      "name": "canonical / parity-inputs (2)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078604"
    },
    {
      "name": "canonical / model-check",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078570"
    },
    {
      "name": "canonical / checks",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125718078529"
    },
    {
      "name": "CodeQL",
      "status": "completed",
      "conclusion": "neutral",
      "app_id": 57789,
      "details_url": "https://github.com/OpenRAE/rae/runs/125717747682"
    },
    {
      "name": "title-guard",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575410306/job/125717684997"
    },
    {
      "name": "body-guard",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575410286/job/125717675871"
    },
    {
      "name": "canonical / generic-tool-local-inputs",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717644505"
    },
    {
      "name": "canonical / test-shard (4)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581866"
    },
    {
      "name": "canonical / test-shard (1)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581389"
    },
    {
      "name": "canonical / test-shard (2)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581370"
    },
    {
      "name": "runtime-supervision",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581312"
    },
    {
      "name": "supply-chain",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581302"
    },
    {
      "name": "canonical / test-shard (0)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581297"
    },
    {
      "name": "CPython 3.14 compatibility",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581286"
    },
    {
      "name": "canonical / go (product, implementations/go)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581280"
    },
    {
      "name": "canonical / test-shard (5)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581277"
    },
    {
      "name": "canonical / test-shard (7)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581263"
    },
    {
      "name": "canonical / test-shard (6)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581252"
    },
    {
      "name": "canonical / test-shard (3)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581250"
    },
    {
      "name": "fuzz",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581206"
    },
    {
      "name": "canonical / proof-archive",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581183"
    },
    {
      "name": "canonical / go-architecture",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581162"
    },
    {
      "name": "canonical / go (tooling, implementations/tooling/go)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717581137"
    },
    {
      "name": "fast-feedback",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391874/job/125717580997"
    },
    {
      "name": "body-guard",
      "status": "completed",
      "conclusion": "cancelled",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391806/job/125717580786"
    },
    {
      "name": "release-classification",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391826/job/125717580539"
    },
    {
      "name": "build",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391804/job/125717580529"
    },
    {
      "name": "title-guard",
      "status": "completed",
      "conclusion": "cancelled",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575391794/job/125717580504"
    },
    {
      "name": "Analyze (javascript-typescript)",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575390308/job/125717579337"
    },
    {
      "name": "Analyze (actions)",
      "status": "completed",
      "conclusion": "success",
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575390308/job/125717579294"
    },
    {
      "name": "GitGuardian Security Checks",
      "status": "completed",
      "conclusion": "success",
      "app_id": 46505,
      "details_url": "https://dashboard.gitguardian.com"
    },
    {
      "name": "Analyze (python)",
      "status": "in_progress",
      "conclusion": null,
      "app_id": 15368,
      "details_url": "https://github.com/OpenRAE/rae/actions/runs/41575390308/job/125717579171"
    }
  ]
}
```
