---
paths:
  - "backend/src/**/*.java"
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.tsx"
---

## Implementation standards

The path filter above does not select the current Python source tree.
Use root `AGENTS.md` and the repository coding standards for current Python work.

- Never take shortcuts. Implement features properly and completely.
  Use complete implementations and verify their behavior.

- Never recommend deferring a fix or improvement "for later" or
  "in a follow-up". If something is broken or missing, fix it now.
  Tech debt has zero justification when the fix is within reach.

- Always check your implementation against the full requirement
  statement clause by clause before declaring completion.

- When you encounter an architectural decision, prefer the approach
  that follows existing patterns in the codebase over inventing
  something new. Read surrounding code first.

- Do not add unnecessary abstractions, indirection layers, or
  "extensibility" that is not required by the current task. Three
  similar lines of code are better than a premature abstraction.

- Do not create stub or placeholder implementations that "will be
  filled in later." Either implement it fully or do not create it.
