# CLAUDE.md

Instructions for Claude Code sessions working in this repository.

## Checks: quick by default, full check on request
Operator decision 2026-09-28. Speed and GitHub Actions cost come first. An
occasional break that is fixed forward is acceptable; running every test on
every change is not. Work in QUICK mode unless the operator says "full check"
or "release". Decide the check yourself and never ask which one to run. This
section overrides any older instruction in this file to run the whole suite
before every push, except where this file names a check that must always
pass (a clinical hazard test, a tenancy or audit guard, a boot probe): keep
those in every mode.

QUICK (the default, every change):
- Lint and typecheck the code you touched and run the tests for that code.
  Not the whole suite.
- Then commit and push straight to the branch this project deploys from,
  without asking and without a pull request (every pull request runs CI
  again), so the change goes live. If this project deploys with a command
  rather than on push, run that command after pushing.
- Batch several changes into one push rather than pushing after every commit.
- Do not sit waiting on CI or the deploy. Carry on, check the result when it
  lands, and fix forward if it is red.

ADD A CHECK YOURSELF, say so in one line, and carry on, when a change touches:
- database migrations or the schema: the project's migration tests;
- login, permissions, keeping customers' data apart, audit, payments or
  money, or clinical and patient data: every test in that area, not just the
  ones beside the change;
- shared types or API definitions used by several packages: a typecheck of
  every package;
- dependencies (package manifests or lockfiles): the tests of each affected
  package;
- infrastructure as code: its format and validate commands;
- more than three packages, or a large rename or move: the full check.

STOP AND ASK only when:
- a migration drops, renames or rewrites existing data;
- the work would apply infrastructure, change a live database by hand, or
  send anything to a real person;
- a product or business decision the code cannot answer.

FULL CHECK (when the operator says "full check"): every test, typecheck and
lint this project has. Fix whatever is red and catch up the docs.

RELEASE (when the operator says "release"): the full check, then this
project's release route.

If this project has gone about a week of quick pushes without a full check,
suggest one in a single closing line and carry on without waiting.
