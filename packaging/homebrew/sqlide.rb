# Homebrew formula for sqlide. Installs the published wheels from PyPI into a virtualenv
# (no compiling of the Python dependencies, so the install is fast).
class Sqlide < Formula
  include Language::Python::Virtualenv

  desc "Terminal SQL IDE (DataGrip-like) over JDBC"
  homepage "https://github.com/XFaIT/sqlide"
  url "https://files.pythonhosted.org/packages/1c/6b/2865efc6243c41e0f96435e5356e5c7d21cdeb50a3dc67540b15ec9ed81f/sqlide-0.1.1.tar.gz"
  sha256 "179f9d668918c78f0dde77e3d4c25ef52573cbf2ebffcd85a41b95949e7a010a"
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
