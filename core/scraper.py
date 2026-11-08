import base64
import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx

BASE_URL = os.getenv("ANIMETUI_BASE_URL", "https://v2.samehadaku.how")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}

M3U8_REGEX = re.compile(r"""https?://[^\s'\"<>\\]+?\.m3u8[^\s'\"<>\\]*""", re.IGNORECASE)


def unpack_packed_js(script: str) -> str:
    pattern = r"""eval\(function\(p,a,c,k,e,[rd]\)\s*\{.*?\}\s*\(\s*['"](.*?)['"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*['"](.*?)['"]\.split\(['"]\|['"]\)\s*,\s*(\d+)\s*,\s*(\{\}|\[\])\s*\)\)"""
    match = re.search(pattern, script, re.DOTALL)
    if not match:
        return script
    payload, radix_str, count_str, symtab, offset_str, _ = match.groups()
    radix = int(radix_str)
    count = int(count_str)
    words = symtab.split("|")

    def base_encode(num: int, b: int) -> str:
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if num == 0:
            return chars[0]
        res = []
        while num > 0:
            res.append(chars[num % b])
            num //= b
        return "".join(reversed(res))

    d = {}
    for c in range(count):
        k = base_encode(c, radix)
        d[k] = words[c] if c < len(words) and words[c] else k

    return re.sub(r"\b\w+\b", lambda m: d.get(m.group(0), m.group(0)), payload)


def decode_potential_base64(val: str) -> str:
    val = val.strip()
    if val.startswith("http://") or val.startswith("https://") or val.startswith("//"):
        return val
    try:
        raw = base64.b64decode(val).decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "html.parser")
        iframe = soup.select_one("iframe")
        if iframe and iframe.get("src"):
            return iframe["src"]
        match = re.search(r"""https?://[^\s'\"<>]+""", raw)
        if match:
            return match.group(0)
    except Exception:
        pass
    return val


async def fetch_html(url: str, referer: str | None = None) -> str:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer

    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def search_content(query: str) -> list[dict]:
    if not query.strip():
        return []

    search_url = f"{BASE_URL.rstrip('/')}/?s={query.strip().replace(' ', '+')}"

    try:
        html = await fetch_html(search_url)
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.select(".animepost, article.animposx, .bsx, article")
    for card in cards:
        link_elem = card.select_one("a[href]")
        if not link_elem:
            continue

        href = link_elem.get("href", "").strip()
        title_elem = card.select_one(".title, .entry-title, h2, h3, h4") or link_elem
        title = title_elem.get_text(strip=True) if title_elem else ""

        if not title and link_elem.get("title"):
            title = link_elem["title"].strip()

        if not title or not href:
            continue

        status_elem = card.select_one(".status, .type, .bt.status, .epx, .eggtype")
        status = status_elem.get_text(strip=True) if status_elem else "N/A"

        img_elem = card.select_one("img")
        thumb = img_elem.get("src") or img_elem.get("data-src", "") if img_elem else ""

        results.append({
            "title": title,
            "url": urljoin(BASE_URL, href),
            "status": status,
            "thumb": thumb,
        })

    return results


async def get_episodes(anime_url: str) -> list[dict]:
    try:
        html = await fetch_html(anime_url)
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    episodes = []

    items = soup.select(".lastep ul li, .epslist ul li, .eplister ul li, ul.episodelist li")
    if not items:
        links = soup.find_all("a", href=re.compile(r"/(?:episode|eps)/|[0-9]+-sub-indo"))
        for a in links:
            t = a.get_text(strip=True) or a.get("title", "")
            h = a.get("href", "")
            if t and h:
                episodes.append({
                    "title": t,
                    "url": urljoin(BASE_URL, h),
                    "date": "N/A",
                })
        return episodes

    for item in items:
        link_elem = item.select_one("a[href]")
        if not link_elem:
            continue

        href = link_elem.get("href", "").strip()
        title_elem = item.select_one(".eps a, .epl-title, .title") or link_elem
        title = title_elem.get_text(strip=True) if title_elem else link_elem.get("title", "")

        date_elem = item.select_one(".date, .epl-date")
        date_str = date_elem.get_text(strip=True) if date_elem else "N/A"

        if title and href:
            episodes.append({
                "title": title,
                "url": urljoin(BASE_URL, href),
                "date": date_str,
            })

    return episodes


async def extract_stream_url(episode_url: str) -> tuple[str | None, str]:
    try:
        html = await fetch_html(episode_url)
    except Exception:
        return None, episode_url

    soup = BeautifulSoup(html, "html.parser")

    # 1. Search for iframe or server options
    iframe = soup.select_one("iframe#embed_holder, .player-iframe, iframe[src]")
    iframe_src = ""

    if iframe:
        iframe_src = iframe.get("src") or iframe.get("data-src", "")

    if not iframe_src:
        server_option = soup.select_one("#server option, select.mirror option, .server option")
        if server_option:
            raw_val = (
                server_option.get("data-embed")
                or server_option.get("value")
                or server_option.get("data-src", "")
            )
            if raw_val:
                iframe_src = decode_potential_base64(raw_val)

    if not iframe_src:
        # Check fallback iframe tags
        all_iframes = soup.find_all("iframe")
        for f in all_iframes:
            src = f.get("src", "")
            if src and not any(bad in src for bad in ("disqus", "facebook", "twitter", "ads")):
                iframe_src = src
                break

    # Format protocol-relative URL
    if iframe_src.startswith("//"):
        iframe_src = "https:" + iframe_src
    elif iframe_src and not iframe_src.startswith("http"):
        iframe_src = urljoin(episode_url, iframe_src)

    # 2. Check if iframe points to Kwik
    if iframe_src and "kwik" in iframe_src.lower():
        try:
            kwik_html = await fetch_html(iframe_src, referer=episode_url)
            # Unpack if packed JS
            if "eval(function(p,a,c,k,e," in kwik_html:
                unpacked = unpack_packed_js(kwik_html)
            else:
                unpacked = kwik_html

            match = M3U8_REGEX.search(unpacked)
            if match:
                stream_link = match.group(0).rstrip("\\'\"")
                return stream_link, iframe_src
        except Exception:
            pass

    # 3. If iframe is present and not kwik, check if it directly contains an m3u8 or video
    if iframe_src:
        if iframe_src.endswith(".m3u8"):
            return iframe_src, episode_url
        try:
            embed_html = await fetch_html(iframe_src, referer=episode_url)
            if "eval(function(p,a,c,k,e," in embed_html:
                embed_html = unpack_packed_js(embed_html)
            match = M3U8_REGEX.search(embed_html)
            if match:
                return match.group(0).rstrip("\\'\""), iframe_src
        except Exception:
            pass
        return iframe_src, episode_url

    # 4. Direct video or script in page
    match = M3U8_REGEX.search(html)
    if match:
        return match.group(0).rstrip("\\'\""), episode_url

    video = soup.select_one("video source[src], video[src]")
    if video:
        return video.get("src"), episode_url

    return None, episode_url
