from __future__ import annotations

import logging
import re
from html import unescape
from typing import TYPE_CHECKING
from urllib.parse import urljoin

if TYPE_CHECKING:
    from hermes.config import TelegramConfig

logger = logging.getLogger(__name__)

_LOGO_PATH_HINTS = ("logo", "icon", "favicon", "avatar", "sprite", "emoji", "gravatar")
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_RE = re.compile(r"""src\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE)
_WIDTH_RE = re.compile(r"""\bwidth\s*=\s*['"]?(\d+)""", re.IGNORECASE)
_HEIGHT_RE = re.compile(r"""\bheight\s*=\s*['"]?(\d+)""", re.IGNORECASE)
_STYLE_WIDTH_RE = re.compile(r"""width\s*:\s*(\d+)""", re.IGNORECASE)
_STYLE_HEIGHT_RE = re.compile(r"""height\s*:\s*(\d+)""", re.IGNORECASE)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(
    r"""([a-zA-Z_:][a-zA-Z0-9_:\-]*)\s*=\s*["']([^"']*)["']""",
    re.IGNORECASE,
)
_TOPJOBS_GENERIC_OG = frozenset(
    {
        "https://topjobs.lk/images/public/tj.jpg",
    }
)


def absolutize(base_url: str, src: str) -> str:
    src = unescape((src or "").strip())
    if not src:
        return ""
    return urljoin(base_url, src)


def is_usable_telegram_photo_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower().strip()
    if lower.startswith("data:"):
        return False
    if lower.startswith("http://"):
        return False
    return lower.startswith("https://")


def looks_like_logo_url(url: str) -> bool:
    """Generic sites: reject obvious logo/icon filenames and paths."""
    lower = url.lower().split("?", 1)[0]
    filename = lower.rsplit("/", 1)[-1]
    if any(hint in filename for hint in _LOGO_PATH_HINTS):
        return True
    if any(
        fragment in lower
        for fragment in ("/favicon", "/icons/", "sprite", "gravatar", "loading.gif")
    ):
        return True
    return False


def looks_like_logo_url_topjobs(url: str) -> bool:
    """TopJobs vacancy creatives live under /logo/{code}/…cABOUTS.png — not icons."""
    lower = url.lower().split("?", 1)[0]
    if "topjobs.lk" in lower and "/logo/" in lower:
        if "abouts" in lower or re.search(r"/logo/[^/]+/\d+c", lower):
            return False
    return looks_like_logo_url(url)


def _img_dimensions(tag: str, *, include_style: bool) -> tuple[int | None, int | None]:
    w_m, h_m = _WIDTH_RE.search(tag), _HEIGHT_RE.search(tag)
    width = int(w_m.group(1)) if w_m else None
    height = int(h_m.group(1)) if h_m else None
    if include_style:
        if width is None:
            sm = _STYLE_WIDTH_RE.search(tag)
            width = int(sm.group(1)) if sm else None
        if height is None:
            sm = _STYLE_HEIGHT_RE.search(tag)
            height = int(sm.group(1)) if sm else None
    return width, height


def _is_decorative_topjobs_img(url: str) -> bool:
    lower = url.lower()
    skip = (
        "loading.gif",
        "info.png",
        "application.png",
        "local.jpg",
        "defzzz_small",
        "/banner/",
        "googletagmanager",
    )
    return any(part in lower for part in skip)


def _og_image_urls(html: str) -> list[str]:
    urls: list[str] = []
    for tag in _META_TAG_RE.findall(html):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(tag)}
        prop = attrs.get("property", "") or attrs.get("name", "")
        if prop.lower() != "og:image":
            continue
        content = (attrs.get("content") or "").strip()
        if content:
            urls.append(content)
    return urls


def accept_media_url(
    url: str,
    *,
    width: int | None,
    height: int | None,
    telegram: TelegramConfig,
    topjobs: bool = False,
) -> bool:
    if not is_usable_telegram_photo_url(url):
        return False
    if not telegram.poster_only:
        return True
    if topjobs:
        if looks_like_logo_url_topjobs(url):
            return False
    elif looks_like_logo_url(url):
        return False
    if width is not None and height is not None:
        if width < telegram.min_image_width or height < telegram.min_image_height:
            return False
        return True
    return True


def _best_img_from_html(
    html: str,
    base_url: str,
    *,
    telegram: TelegramConfig,
    topjobs: bool,
) -> str | None:
    if not html:
        return None

    best_url: str | None = None
    best_area = 0
    include_style = topjobs

    for tag in _IMG_TAG_RE.findall(html):
        src_m = _SRC_RE.search(tag)
        if not src_m:
            continue
        url = absolutize(base_url, src_m.group(1))
        if topjobs and _is_decorative_topjobs_img(url):
            continue
        width, height = _img_dimensions(tag, include_style=include_style)
        area = (width or 0) * (height or 0)
        if not accept_media_url(
            url,
            width=width,
            height=height,
            telegram=telegram,
            topjobs=topjobs,
        ):
            continue
        if area > best_area or best_url is None:
            best_url = url
            best_area = area if area else best_area

    return best_url


def best_poster_from_html(
    html: str,
    base_url: str,
    *,
    telegram: TelegramConfig,
) -> str | None:
    """Jobseeker and other non-TopJobs HTML (no TopJobs /logo/ rules)."""
    if not html:
        return None

    poster = _best_img_from_html(html, base_url, telegram=telegram, topjobs=False)
    if poster:
        return poster

    for raw in _og_image_urls(html):
        normalized = absolutize(base_url, raw)
        if accept_media_url(
            normalized, width=None, height=None, telegram=telegram, topjobs=False
        ):
            return normalized
    return None


def poster_from_topjobs_html(
    html: str,
    base_url: str,
    *,
    telegram: TelegramConfig,
) -> str | None:
    """TopJobs advert servlet: /logo/…cABOUTS flyers, CSS dimensions, skip site og:image."""
    poster = _best_img_from_html(html, base_url, telegram=telegram, topjobs=True)
    if poster:
        return poster

    for raw in _og_image_urls(html):
        normalized = absolutize(base_url, raw)
        if normalized.lower().rstrip("/") in _TOPJOBS_GENERIC_OG:
            continue
        if accept_media_url(
            normalized, width=None, height=None, telegram=telegram, topjobs=True
        ):
            return normalized
    return None


# Backwards-compatible alias for enrich TopJobs path
def og_image_from_html(html: str, base_url: str, *, telegram: TelegramConfig) -> str | None:
    if "topjobs.lk" in base_url.lower():
        return poster_from_topjobs_html(html, base_url, telegram=telegram)
    return best_poster_from_html(html, base_url, telegram=telegram)
