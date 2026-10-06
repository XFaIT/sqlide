# Homebrew

`sqlide.rb` is the formula for sqlide 0.1.0 (url, sha256 and resources filled in) for a tap (`brew tap XFaIT/sqlide`).

1. Release to PyPI (push a `v*` tag; `.github/workflows/release.yml` publishes).
2. Create the repository `homebrew-sqlide` and put the formula in `Formula/sqlide.rb`.
3. For a later release, update `url` and `sha256` from the PyPI sdist, then run
   `brew update-python-resources sqlide` to refresh the resources.
4. `brew install --build-from-source XFaIT/sqlide/sqlide && brew test sqlide`.

Users then run `brew install XFaIT/sqlide/sqlide`.
