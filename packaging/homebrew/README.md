# Homebrew

`sqlide.rb` is a template for a tap (`brew tap OWNER/sqlide`).

1. Release to PyPI (push a `v*` tag; `.github/workflows/release.yml` publishes).
2. Create the repository `homebrew-sqlide` and put the formula in `Formula/sqlide.rb`.
3. Set `url` and `sha256` from the PyPI sdist, then run
   `brew update-python-resources sqlide` to add the dependency resources.
4. `brew install --build-from-source OWNER/sqlide/sqlide && brew test sqlide`.

Users then run `brew install OWNER/sqlide/sqlide`.
