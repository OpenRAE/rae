# Apply the merge queue settings

Use this procedure to make the GitHub settings agree with
`implementations/tooling/branch-merge-policy.json` (ADR-122).
The CI token cannot read these settings, so the policy gate checks only the declaration and the workflows.
You need administrator access to the repository.

## Provide the GitGuardian key to ggshield

Do this step before the workflow change merges.
The ggshield job fails on each pull request until the key is available.

1. Create a GitGuardian API key with the `scan` scope.
2. Add the key as the `GITGUARDIAN_API_KEY` Actions secret.
3. Add the same key as the `GITGUARDIAN_API_KEY` Dependabot secret.

Dependabot pull requests read only Dependabot secrets.
A pull request from a fork has no access to the key, so its `GitGuardian Security Checks` context fails.

## Move CodeQL to advanced setup

Do this step and the next step after the workflow change merges into `dev`.
The queue needs the `merge_group` triggers on `dev`.

Code scanning default setup does not run on merge groups.
Do steps 2 and 3 of the [CodeQL rollout](codeql.md#rollout).
After the switch, `codeql.yml` produces the `CodeQL`, `Analyze (actions)`, and `Analyze (python)` contexts.

## Turn on the merge queue for dev

1. In the `merge-policy-dev` ruleset, add the **Require merge queue** rule.
2. Set the merge method to **Squash**.
3. Set the maximum group size to a value greater than 1.
4. Select **Only merge non-failing pull requests**.
5. In the `dev` branch protection, bind the `GitGuardian Security Checks` required check to **GitHub Actions**.
6. Keep **Require branches to be up to date before merging** off for `dev`.

Keep every other required check on `dev`.
Do not add a merge queue to `main`.
Turn on **Require branches to be up to date before merging** for `main`.

## Check the result

1. Add a ready pull request to the queue.
2. Make sure that each required context reports on the merge group commit.
3. Make sure that the queue merges the pull request only after all required contexts pass.
