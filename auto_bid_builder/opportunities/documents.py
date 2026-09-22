from __future__ import annotations

from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import ipaddress
import mimetypes
from pathlib import Path
import re
import socket
import tempfile
from typing import Iterable
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from ..bid_workspace import add_documents


USER_AGENT = "AutoBidBuilder/0.4 (+https://github.com/CaMaLabs/Auto_Bid_Builder)"
DOWNLOADABLE_EXTENSIONS = {
    ".pdf", ".zip", ".dwg", ".dxf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt"
}
DOWNLOADABLE_CONTENT_TYPES = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.ms-excel",
    "application/octet-stream",
}


@dataclass
class ProjectFilePullResult:
    discovered_urls: list[str] = field(default_factory=list)
    downloaded_files: list[str] = field(default_factory=list)
    skipped_urls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def downloaded_count(self) -> int:
        return len(self.downloaded_files)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["downloaded_count"] = self.downloaded_count
        return data


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []
        self.links_with_text: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = urljoin(self.base_url, href)
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        url = self._href
        text = " ".join("".join(self._parts).split())
        self.links.append(url)
        self.links_with_text.append((url, text))
        self._href = None
        self._parts = []


def _is_public_http_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except OSError:
        return False
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not address.is_global:
            return False
    return True


def _candidate_filename(url: str, headers) -> str:
    disposition = headers.get("Content-Disposition", "") if headers else ""
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if match:
        name = unquote(match.group(1).strip().strip('"'))
    else:
        name = unquote(Path(urlsplit(url).path).name)
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name).strip(" .")
    content_type = (headers.get_content_type() if headers else "") or ""
    if not Path(name).suffix:
        extension = mimetypes.guess_extension(content_type) or ""
        if extension:
            name += extension
    return name or "project_file"


def _looks_like_file_url(url: str) -> bool:
    return Path(urlsplit(url).path).suffix.lower() in DOWNLOADABLE_EXTENSIONS


def _request(url: str, *, timeout: float, opener=None):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/pdf,application/zip,application/octet-stream,*/*",
        },
    )
    if opener is not None:
        return opener.open(request, timeout=timeout)  # nosec B310 - URL is validated before use
    return urlopen(request, timeout=timeout)  # nosec B310 - URLs are validated as public HTTP(S)


def _cookie_opener():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def _read_html(url: str, *, timeout: float, max_html_bytes: int, opener=None) -> tuple[str, str]:
    if not _is_public_http_url(url):
        raise ValueError("URL is not a public HTTP(S) address")
    with _request(url, timeout=timeout, opener=opener) as response:
        content_type = response.headers.get_content_type()
        final_url = response.geturl()
        if content_type in DOWNLOADABLE_CONTENT_TYPES or _looks_like_file_url(final_url):
            return final_url, ""
        body = response.read(max_html_bytes + 1)
        if len(body) > max_html_bytes:
            raise ValueError("listing page exceeded HTML safety limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return final_url, body.decode(charset, errors="replace")


def discover_listing_files(
    url: str,
    *,
    timeout: float = 25.0,
    max_html_bytes: int = 4_000_000,
    opener=None,
) -> list[str]:
    """Return direct-looking document links from one public opportunity page.

    This intentionally does not submit forms, bypass logins, execute JavaScript, or
    recursively crawl a site. Provider-specific public event-package support is
    handled separately.
    """
    if not _is_public_http_url(url):
        return []
    final_url, html = _read_html(url, timeout=timeout, max_html_bytes=max_html_bytes, opener=opener)
    if not html:
        return [final_url] if _looks_like_file_url(final_url) else []
    parser = _LinkParser(final_url)
    parser.feed(html)
    output: list[str] = []
    seen: set[str] = set()
    for link in parser.links:
        if link in seen or not _is_public_http_url(link):
            continue
        if _looks_like_file_url(link):
            seen.add(link)
            output.append(link)
    return output


def _caleprocure_event_parts(url: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (parsed.hostname or "").lower() not in {"caleprocure.ca.gov", "www.caleprocure.ca.gov"}:
        return None
    match = re.match(r"^/event/([^/]+)/([^/?#]+)", parsed.path, re.I)
    if not match:
        return None
    return unquote(match.group(1)), unquote(match.group(2))


def _caleprocure_package_url(url: str) -> str | None:
    parts = _caleprocure_event_parts(url)
    if parts is None:
        return None
    business_unit, event_id = parts
    return (
        "https://caleprocure.ca.gov/PSRelay/AUC_MANAGE_BIDS.AUC_RESP_INQ_AUC.GBL"
        f"?Page=AUC_RESP_INQ_AUC&Action=U&BUSINESS_UNIT={quote(business_unit)}&AUC_ID={quote(event_id)}"
    )


def _looks_like_caleprocure_download(link: str, text: str) -> bool:
    if _looks_like_file_url(link):
        return True
    haystack = f"{link} {text}".lower()
    phrases = (
        "download attachment",
        "download file",
        "attachment",
        "auc_attachments",
        "auc_attachment",
        "file_download",
        "downloadattachment",
    )
    return any(phrase in haystack for phrase in phrases)


def discover_caleprocure_event_files(
    url: str,
    *,
    timeout: float = 30.0,
    max_html_bytes: int = 6_000_000,
    opener=None,
) -> list[str]:
    """Discover public Cal eProcure files behind the event's View Event Package page.

    Cal eProcure's friendly event URL does not expose its bid documents as direct file
    links. The public site routes users through a PeopleSoft "View Event Package"
    page. This helper follows that same public guest route while preserving cookies.
    It does not log in, submit a bid, or bypass any access control.
    """
    package_url = _caleprocure_package_url(url)
    if package_url is None:
        return []
    session = opener or _cookie_opener()

    # Establish the same guest session a normal browser gets from the friendly page.
    try:
        _read_html(url, timeout=timeout, max_html_bytes=max_html_bytes, opener=session)
    except Exception:
        # The friendly shell occasionally rejects non-browser clients while the
        # public event-package relay remains reachable. Try the relay anyway.
        pass

    final_url, html = _read_html(package_url, timeout=timeout, max_html_bytes=max_html_bytes, opener=session)
    if not html:
        return [final_url] if _looks_like_file_url(final_url) else []

    parser = _LinkParser(final_url)
    parser.feed(html)
    output: list[str] = []
    seen: set[str] = set()
    for link, text in parser.links_with_text:
        if link in seen or not _is_public_http_url(link):
            continue
        if _looks_like_caleprocure_download(link, text):
            seen.add(link)
            output.append(link)
    return output


def _download(url: str, destination: Path, *, timeout: float, max_bytes: int, opener=None) -> Path | None:
    if not _is_public_http_url(url):
        return None
    with _request(url, timeout=timeout, opener=opener) as response:
        content_type = response.headers.get_content_type()
        final_url = response.geturl()
        is_file = content_type in DOWNLOADABLE_CONTENT_TYPES or _looks_like_file_url(final_url)
        if not is_file:
            return None
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError(f"file exceeds {max_bytes // (1024 * 1024)} MB safety limit")
        name = _candidate_filename(final_url, response.headers)
        target = destination / name
        index = 2
        while target.exists():
            target = destination / f"{Path(name).stem} ({index}){Path(name).suffix}"
            index += 1
        total = 0
        with target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise ValueError(f"file exceeds {max_bytes // (1024 * 1024)} MB safety limit")
                handle.write(chunk)
        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            return None
        return target


def _unique_urls(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        url = str(value or "").strip()
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def pull_opportunity_documents(
    root: str | Path,
    opportunity_row: dict,
    *,
    timeout: float = 30.0,
    max_file_mb: int = 250,
) -> ProjectFilePullResult:
    """Best-effort download of public project files already linked by an opportunity.

    Direct attachment URLs are tried first. The public listing itself is inspected one
    level deep for obvious document links. Cal eProcure event URLs additionally follow
    the public guest "View Event Package" route. Authentication boundaries are
    respected: a login page simply produces no downloadable files and the user can use
    the normal manual/provider-login workflow instead.
    """
    result = ProjectFilePullResult()
    opportunity = opportunity_row.get("opportunity", opportunity_row)
    direct = list(opportunity.get("attachments") or [])
    listing = str(opportunity.get("url") or "").strip()
    is_caleprocure = _caleprocure_event_parts(listing) is not None if listing else False
    session = _cookie_opener() if is_caleprocure else None

    discovered: list[str] = []
    for url in direct:
        value = str(url or "").strip()
        if not value:
            continue
        if _looks_like_file_url(value):
            discovered.append(value)
        else:
            try:
                nested = discover_listing_files(value, timeout=timeout, opener=session)
            except Exception as exc:
                result.errors.append(f"{value}: {type(exc).__name__}: {exc}")
            else:
                discovered.extend(nested or [value])

    if listing:
        try:
            discovered.extend(discover_listing_files(listing, timeout=timeout, opener=session))
        except Exception as exc:
            result.errors.append(f"{listing}: {type(exc).__name__}: {exc}")

        if is_caleprocure:
            try:
                discovered.extend(discover_caleprocure_event_files(listing, timeout=timeout, opener=session))
            except Exception as exc:
                result.errors.append(f"Cal eProcure event package: {type(exc).__name__}: {exc}")

    result.discovered_urls = _unique_urls(discovered)
    if not result.discovered_urls:
        return result

    max_bytes = max(1, int(max_file_mb)) * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="auto_bid_builder_download_") as tmp:
        tmpdir = Path(tmp)
        downloaded: list[Path] = []
        for url in result.discovered_urls:
            try:
                path = _download(url, tmpdir, timeout=timeout, max_bytes=max_bytes, opener=session)
            except Exception as exc:
                result.errors.append(f"{url}: {type(exc).__name__}: {exc}")
                continue
            if path is None:
                result.skipped_urls.append(url)
                continue
            downloaded.append(path)
        added = add_documents(root, downloaded)
        result.downloaded_files = [str(path) for path in added]
    return result
