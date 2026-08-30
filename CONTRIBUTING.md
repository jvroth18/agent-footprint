# Contributing to agent-footprint

Thanks for helping make agent-footprint safer and more useful.

## Branches

`main` is the stable, releasable branch. Changes reach `main` through reviewed
pull requests from short-lived branches:

- `feat/<topic>` for new behavior
- `fix/<topic>` for bug and security fixes
- `docs/<topic>` for documentation-only changes
- `test/<topic>` for test-only changes
- `chore/<topic>` for maintenance

Keep branches focused and delete them after merging. A permanent development
branch is intentionally not used; `main` is the single integration point.

## Development setup

agent-footprint supports Python 3.9 and newer and has no runtime dependencies.

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Validated commits

Before each commit:

1. Run the tests relevant to the change.
2. Run the complete test suite.
3. Review `git diff --check` and the staged diff.
4. Keep generated scan data, dashboards, credentials, and machine-specific
   paths out of the commit.

Before opening a pull request, verify the branch is current with `main` and
that CI passes on every supported Python version.

## Pull requests

Explain the user-visible behavior, security or privacy implications, and the
validation performed. Small, independently reviewable commits are preferred.
