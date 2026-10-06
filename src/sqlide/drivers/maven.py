"""Maven Central client: pick latest stable version, download jar, verify sha1."""

from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import httpx

BASE_URL = os.environ.get("SQLIDE_MAVEN_URL", "https://repo1.maven.org/maven2")

Progress = Callable[[int, int | None], None]  # (bytes_done, total_or_None)

_PRE = re.compile(r"^(alpha|beta|rc|cr|m|b|ea|dev|preview|snapshot)\d*$", re.I)


class MavenError(Exception):
    pass


def _tokens(version: str) -> list[str]:
    return [t for t in re.split(r"[.\-_]", version) if t]


def is_stable(version: str) -> bool:
    return not any(_PRE.match(t) for t in _tokens(version))


def version_key(version: str) -> tuple:
    """Sortable key: numeric tokens compare as numbers and rank above text tokens."""
    return tuple((1, int(t), "") if t.isdigit() else (0, 0, t) for t in _tokens(version))


def pick_latest(versions: list[str], suffix: str = "") -> str:
    pool = [v for v in versions if is_stable(v) and v.endswith(suffix)]
    if not pool:
        raise MavenError("no stable versions found")
    return max(pool, key=version_key)


def jar_name(artifact: str, version: str, classifier: str) -> str:
    return f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + ".jar"


class MavenClient:
    def __init__(self, client: httpx.Client | None = None, base_url: str = BASE_URL) -> None:
        self._client = client or httpx.Client(timeout=30, follow_redirects=True)
        self._base = base_url.rstrip("/")

    def _dir(self, group: str, artifact: str) -> str:
        return f"{self._base}/{group.replace('.', '/')}/{artifact}"

    def versions(self, group: str, artifact: str) -> list[str]:
        url = f"{self._dir(group, artifact)}/maven-metadata.xml"
        r = self._client.get(url)
        if r.status_code != 200:
            raise MavenError(f"{url}: HTTP {r.status_code}")
        return [v.text or "" for v in ET.fromstring(r.text).iter("version")]

    def latest(self, group: str, artifact: str, suffix: str = "") -> str:
        return pick_latest(self.versions(group, artifact), suffix)

    def find_jar_url(
        self, group: str, artifact: str, version: str, classifiers: list[str]
    ) -> tuple[str, str]:
        """First classifier whose jar exists -> (url, file name)."""
        for c in classifiers or [""]:
            name = jar_name(artifact, version, c)
            url = f"{self._dir(group, artifact)}/{version}/{name}"
            if self._client.head(url).status_code == 200:
                return url, name
        raise MavenError(f"{group}:{artifact}:{version}: no jar for classifiers {classifiers}")

    def download(self, url: str, dest: Path, progress: Progress | None = None) -> Path:
        """Stream to a temp file, verify against <url>.sha1, then rename into place."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        sha = hashlib.sha1()
        try:
            with self._client.stream("GET", url) as r:
                if r.status_code != 200:
                    raise MavenError(f"{url}: HTTP {r.status_code}")
                total = int(r.headers["content-length"]) if "content-length" in r.headers else None
                done = 0
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes(65536):
                        f.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
            self._verify(url, sha.hexdigest())
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return dest

    def _verify(self, url: str, actual: str) -> None:
        r = self._client.get(url + ".sha1")
        if r.status_code != 200:
            raise MavenError(f"{url}.sha1: HTTP {r.status_code}, cannot verify")
        expected = r.text.split()[0].strip().lower() if r.text.strip() else ""
        if expected != actual:
            raise MavenError(f"sha1 mismatch for {url}: expected {expected}, got {actual}")
