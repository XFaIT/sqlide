import hashlib

import httpx
import pytest

from sqlide.drivers.maven import MavenClient, MavenError, is_stable, pick_latest

JAR = b"fake-jar-bytes" * 1000
SHA = hashlib.sha1(JAR).hexdigest()
META = """<metadata><versioning><versions>
<version>0.9.9</version><version>0.10.0</version><version>0.11.0-rc1</version>
</versions></versioning></metadata>"""


def test_stable_filter():
    assert not is_stable("0.11.0-rc1")
    assert not is_stable("1.0.0-SNAPSHOT")
    assert not is_stable("2.0.0.Beta2")
    assert is_stable("0.3.2-patch6")
    assert is_stable("12.8.1.jre11")


def test_pick_latest_numeric_not_lexical():
    assert pick_latest(["0.9.9", "0.10.0", "0.11.0-rc1"]) == "0.10.0"
    assert pick_latest(["0.3.2", "0.3.2-patch6"]) == "0.3.2-patch6"


def test_pick_latest_suffix():
    vs = ["13.6.0.jre8", "13.6.0.jre11", "12.10.0.jre11"]
    assert pick_latest(vs, "jre11") == "13.6.0.jre11"


def test_pick_latest_empty_raises():
    with pytest.raises(MavenError):
        pick_latest(["1.0-rc1"])


def make_client(sha=SHA, jar_status=200):
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("maven-metadata.xml"):
            return httpx.Response(200, text=META)
        if p.endswith("-all-dependencies.jar"):
            return httpx.Response(jar_status, content=JAR if jar_status == 200 else b"")
        if p.endswith(".jar.sha1"):
            return httpx.Response(200, text=sha + "  file")
        return httpx.Response(404)

    return MavenClient(httpx.Client(transport=httpx.MockTransport(handler)), "http://m")


def test_latest_and_classifier_fallback():
    c = make_client()
    assert c.latest("com.clickhouse", "clickhouse-jdbc") == "0.10.0"
    url, name = c.find_jar_url(
        "com.clickhouse", "clickhouse-jdbc", "0.10.0", ["all", "all-dependencies"]
    )
    assert name == "clickhouse-jdbc-0.10.0-all-dependencies.jar"


def test_missing_classifier_raises():
    with pytest.raises(MavenError):
        make_client().find_jar_url("g", "a", "1", ["nope"])


def test_download_ok_with_progress(tmp_path):
    seen = []
    dest = tmp_path / "v" / "a.jar"
    make_client().download("http://m/x-all-dependencies.jar", dest, lambda d, t: seen.append(d))
    assert dest.read_bytes() == JAR and seen[-1] == len(JAR)
    assert not list(dest.parent.glob("*.part"))


def test_download_sha_mismatch_leaves_nothing(tmp_path):
    dest = tmp_path / "v" / "a.jar"
    with pytest.raises(MavenError, match="sha1 mismatch"):
        make_client(sha="0" * 40).download("http://m/x-all-dependencies.jar", dest)
    assert not dest.exists() and not list(dest.parent.glob("*"))
