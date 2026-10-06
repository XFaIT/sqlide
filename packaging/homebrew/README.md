# Homebrew

`sqlide.rb` is the formula, published in the tap `XFaIT/homebrew-sqlide` (`Formula/sqlide.rb`).
It creates a virtualenv and installs the published wheels from PyPI (`pip --only-binary`), so
nothing is compiled. `openjdk` is a dependency; the wrapper script sets `JAVA_HOME`.

Install:

```bash
brew tap XFaIT/sqlide
brew install XFaIT/sqlide/sqlide
```

New release:

1. Push a `v*` tag; `.github/workflows/release.yml` publishes to PyPI.
2. In the formula, update `url` and `sha256` from the PyPI sdist (`sqlide-X.Y.Z.tar.gz`).
   The version is derived from the `url`, and `pip` installs `sqlide==<version>`.
3. Copy the formula to the tap repo. Its CI (`.github/workflows/test.yml`) installs it on macOS
   and Linux and checks `sqlide --version` and Java detection.
