# Homebrew formula for sqlide. Installs the published wheels from PyPI into a virtualenv
# (no compiling of the Python dependencies, so the install is fast).
class Sqlide < Formula
  include Language::Python::Virtualenv

  desc "Terminal SQL IDE (DataGrip-like) over JDBC"
  homepage "https://github.com/XFaIT/sqlide"
  url "https://files.pythonhosted.org/packages/77/ba/dafceab309b6e12db108cc81b8413d527a76db61889539b8562a0b6107c2/sqlide-0.2.0.tar.gz"
  sha256 "d9243b93aabda3360c4de9ee2cc5d3471330f677575c85f0ee9e9da2258fef86"
  license "MIT"

  depends_on "openjdk"
  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    system venv.root/"bin/python", "-m", "pip", "install", "--only-binary=:all:", "sqlide==#{version}"
    # keg-only openjdk is not on PATH: point sqlide at it
    java_home = if OS.mac?
      Formula["openjdk"].opt_libexec/"openjdk.jdk/Contents/Home"
    else
      Formula["openjdk"].opt_prefix
    end
    (bin/"sqlide").write_env_script libexec/"bin/sqlide", JAVA_HOME: java_home
  end

  test do
    assert_match "sqlide", shell_output("#{bin}/sqlide --version")
  end
end
