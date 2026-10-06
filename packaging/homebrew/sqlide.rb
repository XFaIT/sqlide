# Homebrew formula for sqlide 0.1.0. Copy to your tap (homebrew-sqlide/Formula/sqlide.rb).
# Not yet built with brew: run `brew install --build-from-source` and `brew test sqlide` first.
class Sqlide < Formula
  include Language::Python::Virtualenv

  desc "Terminal SQL IDE (DataGrip-like) over JDBC"
  homepage "https://github.com/XFaIT/sqlide"
  url "https://files.pythonhosted.org/packages/37/76/c6fbdb9116c17a5dfe8be4498e6cf7f6f605f9961cd07ef0420f8abd77a3/sqlide-0.1.0.tar.gz"
  sha256 "1648fb530f391ada2019f8590d08efcd5dec04c22b0df4d544088fc24a08302a"
  license "MIT"

  depends_on "openjdk"
  depends_on "python@3.12"

  # Resources below were generated from the dependency closure of sqlide 0.1.0 on PyPI.
  # After a new release, refresh them with `brew update-python-resources sqlide`.

  resource "anyio" do
    url "https://files.pythonhosted.org/packages/a9/d2/f4d173e22df740bc37b1db102b386ba719b66e95b0f0d751f556b387e6d2/anyio-4.15.1.tar.gz"
    sha256 "9f28306018cbd6d329e64a36d58256edff76dd996fe423bc957326e578b82a94"
  end

  resource "certifi" do
    url "https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz"
    sha256 "741e2c3b351ddf169a738da9f2c048608ff7f2c5cc02f1ebc6b118bb090d5d55"
  end

  resource "et-xmlfile" do
    url "https://files.pythonhosted.org/packages/d3/38/af70d7ab1ae9d4da450eeec1fa3918940a5fafb9055e934af8d6eb0c2313/et_xmlfile-2.0.0.tar.gz"
    sha256 "dab3f4764309081ce75662649be815c4c9081e88f0837825f90fd28317d4da54"
  end

  resource "h11" do
    url "https://files.pythonhosted.org/packages/01/ee/02a2c011bdab74c6fb3c75474d40b3052059d95df7e73351460c8588d963/h11-0.16.0.tar.gz"
    sha256 "4e35b956cf45792e4caa5885e69fba00bdbc6ffafbfa020300e549b208ee5ff1"
  end

  resource "httpcore" do
    url "https://files.pythonhosted.org/packages/06/94/82699a10bca87a5556c9c59b5963f2d039dbd239f25bc2a63907a05a14cb/httpcore-1.0.9.tar.gz"
    sha256 "6e34463af53fd2ab5d807f399a9b45ea31c3dfa2276f15a2c3f00afff6e176e8"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/b1/df/48c586a5fe32a0f01324ee087459e112ebb7224f646c0b5023f5e79e9956/httpx-0.28.1.tar.gz"
    sha256 "75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/f5/08/8eea9d4b8302028f3abb2c0813953f7aec26d33b7a8960ed760e65ff29fa/idna-3.20.tar.gz"
    sha256 "a7db850025b95ded1eae8a46181a1a6c56c92c96f0e2b005d9ff8dc0210cab44"
  end

  resource "jpype1" do
    url "https://files.pythonhosted.org/packages/48/a2/5d27e81d24eef64668bf702bfe0e091cc48388b4666f36e025243eb9d827/jpype1-1.7.1.tar.gz"
    sha256 "3cd88838dc3d2d546f7eaeadaaff864e590010c15f2b6a44b6f37e60796a14b2"
  end

  resource "linkify-it-py" do
    url "https://files.pythonhosted.org/packages/45/98/7a1a5f31fd5c7ba93e963b168e244b8e3dd705b3d2a718e3c3307583bf57/linkify_it_py-2.2.0.tar.gz"
    sha256 "907acd2d17ac1fbb9ddb62c8957ccbd6158cac602231a15c3b0cd1e215f03cee"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/06/ff/7841249c247aa650a76b9ee4bbaeae59370dc8bfd2f6c01f3630c35eb134/markdown_it_py-4.2.0.tar.gz"
    sha256 "04a21681d6fbb623de53f6f364d352309d4094dd4194040a10fd51833e418d49"
  end

  resource "mdit-py-plugins" do
    url "https://files.pythonhosted.org/packages/59/fc/f8d0863f8862f25602c0404d75568e89fb6b4109804645e5cdfb1be5cf56/mdit_py_plugins-0.6.1.tar.gz"
    sha256 "a2bca0f039f39dbd35fb74ae1b5f998608c437463371f0ff7f49a19a17a114d0"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "openpyxl" do
    url "https://files.pythonhosted.org/packages/3d/f9/88d94a75de065ea32619465d2f77b29a0469500e99012523b91cc4141cd1/openpyxl-3.1.5.tar.gz"
    sha256 "cf0e3cf56142039133628b5acffe8ef0c12bc902d2aadd3e0fe5878dc08d1050"
  end

  resource "packaging" do
    url "https://files.pythonhosted.org/packages/7d/fa/3944b40b07da9ce895c0e6303a5ab7d53da063554f534556b134a54d6093/packaging-26.3.tar.gz"
    sha256 "94edc256424af38762eb31306eed28beb9f0efc50a8837492c9d6fd6004aed79"
  end

  resource "platformdirs" do
    url "https://files.pythonhosted.org/packages/42/23/4a86fc741c38c5b69792a4ef954b281afa69bea9f083f881de1b0d23bc07/platformdirs-4.12.3.tar.gz"
    sha256 "427fc0bb321ae0c5b037fa03238ca74820437be162e78b4848c4d4055b9b766c"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/49/2e/ced460408999b33da6b31b0021b0f37d329e202d4169aeb164493778f25b/pygments-2.21.0.tar.gz"
    sha256 "610ca751c9bc2492b38eb9a38a7fbc93edbbb2d7182edaf34e66ae493dee5c8c"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/c0/8f/0722ca900cc807c13a6a0c696dacf35430f72e0ec571c4275d2371fca3e9/rich-15.0.0.tar.gz"
    sha256 "edd07a4824c6b40189fb7ac9bc4c52536e9780fbbfbddf6f1e2502c31b068c36"
  end

  resource "sqlglot" do
    url "https://files.pythonhosted.org/packages/11/c0/cd761f018601bf954c9018420eb6707e3675292dfa514cfda44d06aff2ee/sqlglot-30.21.0.tar.gz"
    sha256 "6787ac202a3adc0e25434f1512370a655e51cb3de8c792544de5f6ff9c618d25"
  end

  resource "textual" do
    url "https://files.pythonhosted.org/packages/00/21/39a76b01bd5eea82a04baaca7580e105d8c59450df03998345bb2cfb307b/textual-8.2.8.tar.gz"
    sha256 "3f106a9fbc73e39dd266c9712432087de78a6d644084c7c241d6a25c3169115b"
  end

  resource "tomli-w" do
    url "https://files.pythonhosted.org/packages/19/75/241269d1da26b624c0d5e110e8149093c759b7a286138f4efd61a60e75fe/tomli_w-1.2.0.tar.gz"
    sha256 "2dd14fac5a47c27be9cd4c976af5a12d87fb1f0b4512f81d69cce3b35ae25021"
  end

  resource "tree-sitter" do
    url "https://files.pythonhosted.org/packages/f7/03/5600b84aff2e6c4fe80cfebb4063fe2f50299521befe5f6092ab8c082f4a/tree_sitter-0.26.0.tar.gz"
    sha256 "b40c219edccc4564530c96f8f1556f6202b37cda964d1cbd7bd2b7e68b40a245"
  end

  resource "tree-sitter-bash" do
    url "https://files.pythonhosted.org/packages/8e/0e/f0108be910f1eef6499eabce517e79fe3b12057280ed398da67ce2426cba/tree_sitter_bash-0.25.1.tar.gz"
    sha256 "bfc0bdaa77bc1e86e3c6652e5a6e140c40c0a16b84185c2b63ad7cd809b88f14"
  end

  resource "tree-sitter-css" do
    url "https://files.pythonhosted.org/packages/38/37/7d60171240d4c5ba330f05b725dfb5e5fd5b7cbe0aa98ef9e77f77f868f5/tree_sitter_css-0.25.0.tar.gz"
    sha256 "2fc996bf05b04e06061e88ee4c60837783dc4e62a695205acbc262ee30454138"
  end

  resource "tree-sitter-go" do
    url "https://files.pythonhosted.org/packages/01/05/727308adbbc79bcb1c92fc0ea10556a735f9d0f0a5435a18f59d40f7fd77/tree_sitter_go-0.25.0.tar.gz"
    sha256 "a7466e9b8d94dda94cae8d91629f26edb2d26166fd454d4831c3bf6dfa2e8d68"
  end

  resource "tree-sitter-html" do
    url "https://files.pythonhosted.org/packages/04/06/ad1c53c79da15bef85939aa022d72301e12a9773e9bb9a5e6a6f65b7753a/tree_sitter_html-0.23.2.tar.gz"
    sha256 "bc9922defe23144d9146bc1509fcd00d361bf6b3303f9effee6532c6a0296961"
  end

  resource "tree-sitter-java" do
    url "https://files.pythonhosted.org/packages/fa/dc/eb9c8f96304e5d8ae1663126d89967a622a80937ad2909903569ccb7ec8f/tree_sitter_java-0.23.5.tar.gz"
    sha256 "f5cd57b8f1270a7f0438878750d02ccc79421d45cca65ff284f1527e9ef02e38"
  end

  resource "tree-sitter-javascript" do
    url "https://files.pythonhosted.org/packages/59/e0/e63103c72a9d3dfd89a31e02e660263ad84b7438e5f44ee82e443e65bbde/tree_sitter_javascript-0.25.0.tar.gz"
    sha256 "329b5414874f0588a98f1c291f1b28138286617aa907746ffe55adfdcf963f38"
  end

  resource "tree-sitter-json" do
    url "https://files.pythonhosted.org/packages/d7/29/e92df6dca3a6b2ab1c179978be398059817e1173fbacd47e832aaff3446b/tree_sitter_json-0.24.8.tar.gz"
    sha256 "ca8486e52e2d261819311d35cf98656123d59008c3b7dcf91e61d2c0c6f3120e"
  end

  resource "tree-sitter-markdown" do
    url "https://files.pythonhosted.org/packages/9a/87/8f705d8f99337c8a691bcc8c22d89ddd323eb2b860a78ae2e894b9f7ade1/tree_sitter_markdown-0.5.1.tar.gz"
    sha256 "6c69d7270a7e09be8988ced44584c09a6a4f541cea0dc394dd1c1a5ac3b5601d"
  end

  resource "tree-sitter-python" do
    url "https://files.pythonhosted.org/packages/b8/8b/c992ff0e768cb6768d5c96234579bf8842b3a633db641455d86dd30d5dac/tree_sitter_python-0.25.0.tar.gz"
    sha256 "b13e090f725f5b9c86aa455a268553c65cadf325471ad5b65cd29cac8a1a68ac"
  end

  resource "tree-sitter-regex" do
    url "https://files.pythonhosted.org/packages/86/92/1767b833518d731b97c07cf616ea15495dcc0af584aa0381657be4ec446d/tree_sitter_regex-0.25.0.tar.gz"
    sha256 "5d29111b3f27d4afb31496476d392d1f562fe0bfe954e8968f1d8683424fc331"
  end

  resource "tree-sitter-rust" do
    url "https://files.pythonhosted.org/packages/b7/87/75cbd22b927267d310f76cca1ab3c1d9d41035dfa3eb9cc95f96ee199440/tree_sitter_rust-0.24.2.tar.gz"
    sha256 "54fb02a5911e345308b405174465112479f56dc39e3f1e7744d7568595f00db9"
  end

  resource "tree-sitter-sql" do
    url "https://files.pythonhosted.org/packages/e8/5c/3d10387f779f36835486167253682f61d5f4fd8336b7001da1ac7d78f31c/tree_sitter_sql-0.3.11.tar.gz"
    sha256 "700b93be2174c3c83d174ec3e10b682f72a4fb451f0076c7ce5012f1d5a76cbc"
  end

  resource "tree-sitter-toml" do
    url "https://files.pythonhosted.org/packages/59/b9/03ee757ac375e77186ea112c14fcf31e0ca70b27b6388d93dcceef61f029/tree_sitter_toml-0.7.0.tar.gz"
    sha256 "29e257612fa8f0c1fcbc4e7e08ddc561169f1725265302e64d81086354144a70"
  end

  resource "tree-sitter-xml" do
    url "https://files.pythonhosted.org/packages/41/ba/77a92dbb4dfb374fb99863a07f938de7509ceeaa74139933ac2bd306eeb1/tree_sitter_xml-0.7.0.tar.gz"
    sha256 "ab0ff396f20230ad8483d968151ce0c35abe193eb023b20fbd8b8ce4cf9e9f61"
  end

  resource "tree-sitter-yaml" do
    url "https://files.pythonhosted.org/packages/57/b6/941d356ac70c90b9d2927375259e3a4204f38f7499ec6e7e8a95b9664689/tree_sitter_yaml-0.7.2.tar.gz"
    sha256 "756db4c09c9d9e97c81699e8f941cb8ce4e51104927f6090eefe638ee567d32c"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3306cebfbda2c520f545d36b5be2c7255cc528bb45d6/typing_extensions-4.16.0.tar.gz"
    sha256 "dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5"
  end

  def install
    virtualenv_install_with_resources
    # keg-only openjdk is not on PATH: point sqlide at it
    java_home = if OS.mac?
      Formula["openjdk"].opt_libexec/"openjdk.jdk/Contents/Home"
    else
      Formula["openjdk"].opt_prefix
    end
    rm bin/"sqlide"
    (bin/"sqlide").write_env_script libexec/"bin/sqlide", JAVA_HOME: java_home
  end

  test do
    assert_match "sqlide", shell_output("#{bin}/sqlide --version")
  end
end
