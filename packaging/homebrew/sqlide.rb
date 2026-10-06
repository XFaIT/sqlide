# Homebrew formula for sqlide. Installs the published wheels from PyPI into a virtualenv
# (no compiling of the Python dependencies, so the install is fast).
class Sqlide < Formula
  include Language::Python::Virtualenv

  desc "Terminal SQL IDE (DataGrip-like) over JDBC"
  homepage "https://github.com/XFaIT/sqlide"
  url "https://files.pythonhosted.org/packages/37/76/c6fbdb9116c17a5dfe8be4498e6cf7f6f605f9961cd07ef0420f8abd77a3/sqlide-0.1.0.tar.gz"
  sha256 "1648fb530f391ada2019f8590d08efcd5dec04c22b0df4d544088fc24a08302a"
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
