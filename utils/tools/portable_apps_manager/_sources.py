"""Release sources. Each source answers: what is the latest release, and which asset to download.

    github  GitHub releases API (/releases/latest), asset picked by a glob/regex
    url     a fixed download URL; changes detected from the redirect target or HTTP headers

A source has release_for(spec) -> ReleaseInfo and resolve(spec, release) -> Asset; a new source
type (e.g. page scrape) is a new class registered in SOURCES.
"""
import datetime
import email.utils
import fnmatch
import os
import re
import urllib.parse
from dataclasses import dataclass

from ._http import session

# Checksum / signature files published next to the real assets - never a download candidate.
_SIDECAR_RE = re.compile(r'(\.(sha\d+|md5|sig|asc|minisig|blockmap|sbom|json)$)|(^(sha\d+)?sums?(\.txt)?$)|checksums?', re.IGNORECASE)
_TIMEOUT = 15


class SourceError(Exception):
    pass


@dataclass
class Asset:
    name: str
    url: str
    size: int
    sha256: str | None       # from GitHub's asset 'digest' field, when present
    updated_at: str
    api_url: str = ''        # GitHub API asset URL: download fallback when the github.com link returns 5xx


@dataclass
class ReleaseInfo:
    version: str              # shown to the user (tag, version from URL, or Last-Modified date)
    published_at: str
    html_url: str
    assets: list[Asset]       # sidecar files (checksums/signatures) already removed
    marker: str = ''          # compared with AppSpec.installed_marker; '' = unknown without downloading


def parse_repo(text: str) -> str:
    """'owner/name' or any github.com URL of the repo -> 'owner/name'."""
    t = text.strip().rstrip('/')
    m = re.match(r'^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)', t, re.IGNORECASE)
    if m:
        owner, name = m.groups()
    else:
        parts = t.split('/')
        if len(parts) != 2 or not all(parts):
            raise SourceError(f'Not a GitHub repo: "{text}" (expected owner/name or a github.com URL)')
        owner, name = parts
    return f'{owner}/{name.removesuffix(".git")}'


def match_assets(pattern: str, assets: list[Asset]) -> list[Asset]:
    """Glob (case-insensitive) on the asset name, or 're:<regex>' for a full-match regex."""
    if pattern.startswith('re:'):
        rx = re.compile(pattern[3:], re.IGNORECASE)
        return [a for a in assets if rx.fullmatch(a.name)]
    p = pattern.lower()
    return [a for a in assets if fnmatch.fnmatchcase(a.name.lower(), p)]


def suggest_name(repo: str, asset_name: str | None = None) -> str:
    """Default app name/folder: the repo name, cased the way the project's asset name spells it
    ('gitextensions/gitextensions' + 'GitExtensions-Portable-x64-7.2.1.zip' -> 'GitExtensions');
    falls back to the repo name as-is when the asset name doesn't contain it."""
    short = repo.split('/')[-1]
    i = asset_name.lower().find(short.lower()) if asset_name else -1
    return asset_name[i:i + len(short)] if i >= 0 else short


def suggest_pattern(asset_name: str, version: str) -> str:
    """Replace the version text inside the asset name with '*' so the pattern survives updates.
    'scrcpy-win64-v3.3.1.zip' + tag 'v3.3.1' -> 'scrcpy-win64-*.zip'."""
    bare = version.lstrip('vV')
    # tag as-is, without leading 'v', and with separators dropped ('24.08' -> '2408' in '7z2408-x64.exe')
    for v in (version, bare, re.sub(r'[.\-_]', '', bare)):
        if v and v in asset_name:
            # also swallow build numbers / commit hashes right after the version:
            # 'GitExtensions-Portable-x64-5.2.1.18061-f2ad1d4f0.zip' -> 'GitExtensions-Portable-x64-*.zip'
            return re.sub(re.escape(v) + r'(?:[.\-_](?:\d+|[0-9a-f]{7,40})(?![0-9a-z]))*', '*', asset_name, count=1)
    # Tag not in the name (e.g. tag '2.48.1.windows.1', asset 'PortableGit-2.48.1-64-bit.7z.exe'):
    # replace dotted version-like runs instead.
    return re.sub(r'\d+(?:\.\d+)+', '*', asset_name)


class GitHubSource:
    kind = 'github'

    def latest_release(self, repo: str) -> ReleaseInfo:
        import requests
        url = f'https://api.github.com/repos/{repo}/releases/latest'
        try:
            r = session().get(url, timeout=_TIMEOUT, headers={'Accept': 'application/vnd.github+json'})
        except requests.RequestException as e:
            raise SourceError(f'{repo}: network error: {e}') from None
        if r.status_code in (403, 429) and r.headers.get('X-RateLimit-Remaining') == '0':
            reset = datetime.datetime.fromtimestamp(int(r.headers.get('X-RateLimit-Reset', '0')))
            raise SourceError(f'GitHub API rate limit reached (60/hour without a token); resets at {reset:%H:%M}')
        if r.status_code == 404:
            raise SourceError(f'{repo}: repo not found, or it has no published (non-prerelease) release')
        if r.status_code != 200:
            raise SourceError(f'{repo}: GitHub API HTTP {r.status_code}: {r.text[:200]}')
        d = r.json()
        assets = [Asset(name=a['name'], url=a['browser_download_url'], size=a.get('size', 0),
                        sha256=(a.get('digest') or '').removeprefix('sha256:') or None,
                        updated_at=a.get('updated_at', ''), api_url=a.get('url', ''))
                  for a in d.get('assets', []) if not _SIDECAR_RE.search(a['name'])]
        return ReleaseInfo(version=d['tag_name'], published_at=d.get('published_at', ''),
                           html_url=d.get('html_url', ''), assets=assets, marker=d['tag_name'])

    def release_for(self, spec) -> ReleaseInfo:
        return self.latest_release(spec.repo)

    def resolve(self, spec, release: ReleaseInfo) -> Asset:
        """The one asset spec.asset selects from release; SourceError on zero or several matches."""
        hits = match_assets(spec.asset, release.assets)
        if len(hits) == 1:
            return hits[0]
        names = '\n  '.join(a.name for a in (hits or release.assets)) or '(none)'
        if not hits:
            raise SourceError(f'"{spec.asset}" matches no asset in {release.version}. Available:\n  {names}')
        raise SourceError(f'"{spec.asset}" matches {len(hits)} assets in {release.version} - make it specific:\n  {names}')


# ── direct URL ────────────────────────────────────────────────────────────────

# How a url app detects a new file, best first. Chosen per app at Add time from what the server sends.
CHECK_MODES = {
    'final_url':     'Version in redirect target (e.g. .../putty/0.85/...)',
    'etag':          'ETag header changes',
    'last_modified': 'Last-Modified header changes',
    'download':      'No usable header - every check downloads the file',
}
_VERSION_TOKEN = re.compile(r'\d+(?:\.\d+)+')
_CD_FILENAME = re.compile(r"""filename\*?=(?:UTF-8'')?"?([^";]+)"?""", re.IGNORECASE)


@dataclass
class UrlProbe:
    url: str
    final_url: str
    filename: str        # what the download will be saved as
    etag: str
    last_modified: str
    size: int
    url_version: str     # version token that the redirect target adds to the URL path, '' if none

    def modes(self) -> list[str]:
        """Usable CHECK_MODES for this server, best first ('download' always works)."""
        return [m for m, ok in (('final_url', self.url_version), ('etag', self.etag),
                                ('last_modified', self.last_modified), ('download', True)) if ok]

    def modified_date(self) -> str:
        try:
            return email.utils.parsedate_to_datetime(self.last_modified).date().isoformat()
        except (TypeError, ValueError):
            return ''


def _url_path(url: str) -> str:
    return urllib.parse.unquote(urllib.parse.urlsplit(url).path)


def probe_url(url: str) -> UrlProbe:
    """HEAD the URL (following redirects); falls back to a 1-byte ranged GET for servers that
    reject HEAD. Nothing is downloaded."""
    import requests
    url = url.strip()
    if not re.match(r'^https?://', url, re.IGNORECASE):
        raise SourceError(f'Not an http(s) URL: "{url}"')
    s = session()
    try:
        r = s.head(url, allow_redirects=True, timeout=_TIMEOUT)
        size = int(r.headers.get('Content-Length') or 0)
        if r.status_code >= 400:
            r = s.get(url, headers={'Range': 'bytes=0-0'}, stream=True, allow_redirects=True, timeout=_TIMEOUT)
            r.close()
            m = re.search(r'/(\d+)$', r.headers.get('Content-Range', ''))
            size = int(m.group(1)) if m else int(r.headers.get('Content-Length') or 0)
    except requests.RequestException as e:
        raise SourceError(f'{url}: network error: {e}') from None
    if r.status_code >= 400:
        raise SourceError(f'{url}: HTTP {r.status_code}')
    cd = _CD_FILENAME.search(r.headers.get('Content-Disposition', ''))
    orig_path, final_path = _url_path(url), _url_path(r.url)
    final_name = os.path.basename(final_path)
    filename = (urllib.parse.unquote(cd.group(1)) if cd else
                final_name if '.' in final_name else os.path.basename(orig_path))
    new_tokens = [t for t in _VERSION_TOKEN.findall(final_path) if t not in orig_path] if final_path != orig_path else []
    return UrlProbe(url=url, final_url=r.url, filename=filename, etag=r.headers.get('ETag', ''),
                    last_modified=r.headers.get('Last-Modified', ''), size=size,
                    url_version=new_tokens[0] if new_tokens else '')


class UrlSource:
    kind = 'url'

    def release_for(self, spec) -> ReleaseInfo:
        return self.release_from_probe(spec, probe_url(spec.url))

    def release_from_probe(self, spec, p: UrlProbe) -> ReleaseInfo:
        mode = spec.check_by or p.modes()[0]
        if mode not in p.modes():
            raise SourceError(f'{spec.url}: check_by = {mode}, but the server no longer provides it '
                              f'(available: {", ".join(p.modes())}) - edit the app')
        marker = {'final_url': _url_path(p.final_url), 'etag': p.etag,
                  'last_modified': p.last_modified, 'download': ''}[mode]
        version = p.url_version if mode == 'final_url' else (p.modified_date() or 'unknown')
        asset = Asset(name=p.filename, url=p.final_url, size=p.size, sha256=None, updated_at=p.last_modified)
        return ReleaseInfo(version=version, published_at=p.last_modified, html_url=spec.url,
                           assets=[asset], marker=marker)

    def resolve(self, spec, release: ReleaseInfo) -> Asset:
        return release.assets[0]


def suggest_name_from_file(filename: str) -> str:
    """'platform-tools-latest-windows.zip' -> 'platform-tools'; 'VSCode-win32-x64-1.145.0.zip' -> 'VSCode'."""
    base = re.sub(r'(\.tar)?\.[A-Za-z0-9]+$', '', filename)
    stop = re.compile(r'^(v?\d[\d.]*|latest|release|stable|nightly|win(dows)?(32|64)?|x64|x86|amd64|arm64|'
                      r'portable|essentials|setup|full|build)$', re.IGNORECASE)
    out = []
    for part in re.split(r'[-_ ]', base):
        if stop.match(part):
            break
        out.append(part)
    return '-'.join(out) or base


SOURCES = {GitHubSource.kind: GitHubSource(), UrlSource.kind: UrlSource()}


def get_source(kind: str):
    try:
        return SOURCES[kind]
    except KeyError:
        raise SourceError(f'Unknown source type "{kind}" (supported: {", ".join(SOURCES)})') from None


def up_to_date(spec, release: ReleaseInfo) -> bool | None:
    """True/False, or None when the source can't tell without downloading (check_by = download)."""
    if not release.marker:
        return None
    # GitHub apps installed before installed_marker existed: the tag was stored as installed_version
    stored = spec.installed_marker or (spec.installed_version if spec.source == 'github' else '')
    return stored == release.marker
