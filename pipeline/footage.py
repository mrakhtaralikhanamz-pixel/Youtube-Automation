"""keyword -> downloaded b-roll clip(s).

Tries sources in the order given by config.FOOTAGE_SOURCES. NASA's Image and
Video Library needs no API key at all (everything on it is public domain).
Pexels and Pixabay need a free API key each (see README setup steps). Internet
Archive needs no key either, but its catalog is a mix of public-domain and
fully copyrighted uploads sitting side by side -- see _from_archive_org for
how that's filtered down to only public-domain items.
"""
import os
import requests

import config

HEADERS_TIMEOUT = 20


def _download(url: str, dest_path: str) -> str:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    return dest_path


def _from_nasa(keyword: str, dest_path: str):
    # No API key required — https://api.nasa.gov/  (Image and Video Library)
    search_url = "https://images-api.nasa.gov/search"
    resp = requests.get(
        search_url, params={"q": keyword, "media_type": "video"}, timeout=HEADERS_TIMEOUT
    )
    resp.raise_for_status()
    items = resp.json().get("collection", {}).get("items", [])
    if not items:
        return None
    nasa_id = items[0]["data"][0]["nasa_id"]
    asset_resp = requests.get(f"https://images-api.nasa.gov/asset/{nasa_id}", timeout=HEADERS_TIMEOUT)
    asset_resp.raise_for_status()
    # Prefer a reasonably-sized mp4 rendition, not the largest master file.
    candidates = [
        item["href"] for item in asset_resp.json()["collection"]["items"] if item["href"].endswith(".mp4")
    ]
    if not candidates:
        return None
    pick = candidates[len(candidates) // 2]  # mid-quality rendition
    return _download(pick, dest_path)


def _from_archive_org(keyword: str, dest_path: str):
    """Internet Archive (archive.org) -- free, no API key, huge catalog including NASA's
    own archival collections. The catch: archive.org hosts everything from public-domain
    films to fully copyrighted uploads side by side, so this is filtered twice --
    once server-side in the search query (licenseurl must mention "publicdomain"), and
    again client-side against the item's actual metadata before ever downloading it.
    Never relax the second check just because the first one already looks restrictive;
    the search filter isn't guaranteed to be airtight and the client-side check is cheap.
    """
    search_url = "https://archive.org/advancedsearch.php"
    query = f"({keyword}) AND mediatype:(movies) AND licenseurl:(*publicdomain*)"
    resp = requests.get(
        search_url,
        params={
            "q": query,
            "fl[]": "identifier",
            "rows": 5,
            "output": "json",
        },
        timeout=HEADERS_TIMEOUT,
    )
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    if not docs:
        return None

    for doc in docs:
        identifier = doc.get("identifier")
        if not identifier:
            continue
        meta_resp = requests.get(f"https://archive.org/metadata/{identifier}", timeout=HEADERS_TIMEOUT)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        license_url = meta.get("metadata", {}).get("licenseurl", "")
        if "publicdomain" not in license_url.lower():
            continue  # server-side filter isn't airtight -- re-verify before trusting an item

        server, item_dir = meta.get("server"), meta.get("dir")
        files = meta.get("files", [])
        if not (server and item_dir and files):
            continue
        candidates = [f["name"] for f in files if f.get("name", "").lower().endswith(".mp4")]
        if not candidates:
            continue
        pick = candidates[len(candidates) // 2]  # mid-quality rendition, same policy as other sources
        return _download(f"https://{server}{item_dir}/{pick}", dest_path)

    return None


def _from_pexels(keyword: str, dest_path: str):
    if not config.PEXELS_API_KEY:
        return None
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": keyword, "per_page": 5, "orientation": "portrait"},
        timeout=HEADERS_TIMEOUT,
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        return None
    files = sorted(videos[0]["video_files"], key=lambda f: f.get("width", 0))
    # pick a mid-resolution file to keep downloads/render times reasonable
    pick = files[len(files) // 2]
    return _download(pick["link"], dest_path)


def _from_pixabay(keyword: str, dest_path: str):
    if not config.PIXABAY_API_KEY:
        return None
    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": config.PIXABAY_API_KEY, "q": keyword, "per_page": 5},
        timeout=HEADERS_TIMEOUT,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return None
    videos = hits[0]["videos"]
    pick = videos.get("medium") or videos.get("small") or list(videos.values())[0]
    return _download(pick["url"], dest_path)


_SOURCE_FUNCS = {
    "nasa": _from_nasa,
    "pexels": _from_pexels,
    "pixabay": _from_pixabay,
    "archive": _from_archive_org,
}


def fetch_clip(keyword: str, dest_path: str) -> str:
    """Try each configured source in order; return the local path of whichever succeeds first."""
    for source_name in config.FOOTAGE_SOURCES:
        func = _SOURCE_FUNCS.get(source_name)
        if not func:
            continue
        try:
            result = func(keyword, dest_path)
            if result:
                return result
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            print(f"  (footage source '{source_name}' failed for '{keyword}': {e}; trying next source)")
            continue
    raise RuntimeError(f"No footage found for keyword '{keyword}' from any configured source.")


def fetch_all(keywords, work_dir: str):
    os.makedirs(work_dir, exist_ok=True)
    paths = []
    for i, kw in enumerate(keywords):
        dest = os.path.join(work_dir, f"clip_{i:02d}.mp4")
        paths.append(fetch_clip(kw, dest))
    return paths
