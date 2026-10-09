# Boundary fixture provenance

A boundary fixture stands in for something this repository does not control.
That can be a platform or third-party API, a command-line tool or subprocess, a
database driver, the filesystem or the operating system, the clock, or another
repository's producer. Such a fixture is evidence only when its shape was
observed from the real system in the state the code handles. A shape written
from documentation or from what the code expects can agree with a wrong
consumer, and the suite then stays green while the behavior cannot work.

This note sets the rule for adding or changing a boundary fixture. The
[fixture provenance audit](../../research/fixture-provenance/index.md) applied
it to the existing suite (issue #1344).

## Capture before you encode

1. Drive the real producer once in the state your code handles and keep what it
   returned. One response is enough. Record the producer and its version, the
   call or command, the state, the date in UTC, and anything you trimmed.
2. Capture the conditional shapes, not only the happy path:
   - an empty or missing value (`null` and `""` are different shapes);
   - the error the producer actually raises or prints, with its exit code and
     what reaches stdout and stderr;
   - counts above one, and repeated runs or retries;
   - mixed precision, ordering and time zones in timestamps;
   - lifecycle preconditions, such as an operation on an object that is already
     stopped or gone.
3. Remove credentials, tokens and signed URL query strings before committing a
   capture.

## Keep the capture where the tests use it

- Put a capture that tests read in its own file under
  `implementations/python/tests/data/`, one file per producer and boundary,
  with the provenance fields inside the file.
- Derive the fake's behavior from the capture instead of retyping its shape.
  For example, a fake for a library binding loads the capture once, returns the
  captured readback and raises the captured error code for a missing object.
- When a test cannot read a capture, state in the fake's docstring where its
  shape came from: the capture, the producer's source file, or the published
  schema. If no real response could be obtained, say so; that fixture is
  inferred and stays listed as such in the inventory.

## Prove the fake reaches reality

- Run the production consumer on the captured response in a test.
- Disable the production branch that handles the real shape and rerun the tests.
  If they stay green, the fake never exercises that branch.
- Do not build the "real" side of an equality or anti-substitution check through
  the code under test. Build it from the producer.

## Keep captures current

- Tie each capture to the code that produced its input. A test that re-renders
  the input and compares it with the capture flags the capture as stale when
  that code changes.
- Re-capture when the producer's version or the input-rendering code changes.
- Never edit a captured artifact by hand. Replace it with a new capture.

## Review question

A change that adds or edits a boundary fixture answers one question in the test
module or the capture file: where did this shape come from? "It is what the code
expects" is not an answer. "It is what the producer returned, in this state, on
this date" is.
