#!/usr/bin/env python3
"""Zotero helper for paper videos (Zotero web API; stdlib only). Writes only ever ADD links, notes and tags.

Key file: ~/.config/paper-video/zotero.json  {"user_id": "...", "api_key": "..."}  (write access)

  zotero.py find <query>          query = Zotero item key | arXiv id | PDF path under ~/Zotero/storage | title words
  zotero.py add-arxiv <id>        create a preprint item from arXiv metadata (if not already in the library)
  zotero.py link <key> <video>    add/refresh the "▶ Video" linked-file attachment + tag "video" (drops "to-video")
  zotero.py queue                 items tagged "to-video" (batch mode)
  zotero.py ensure-search         create the saved search "📺 Papers with videos" if missing
Prints JSON.
"""
import json, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

CONF = Path.home() / ".config/paper-video/zotero.json"
VIDEO_TITLE = "▶ Video"
VIDEO_TAG, QUEUE_TAG = "video", "to-video"
SEARCH_NAME = "📺 Papers with videos"
ARXIV_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


def _conf():
    c = json.loads(CONF.read_text())
    return str(c["user_id"]), c["api_key"]


def api(method, path, body=None, headers=None):
    uid, key = _conf()
    url = f"https://api.zotero.org/users/{uid}{path}"
    h = {"Zotero-API-Key": key, "Zotero-API-Version": "3", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method), timeout=30) as r:
        txt = r.read()
        return json.loads(txt) if txt else None


def _all(path):
    out, start = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        page = api("GET", f"{path}{sep}limit=100&start={start}")
        out += page
        if len(page) < 100:
            return out
        start += 100


def collection_paths():
    cols = {c["key"]: c["data"] for c in _all("/collections")}

    def path(k):
        d = cols[k]
        return (path(d["parentCollection"]) + "/" if d.get("parentCollection") else "") + d["name"]
    return {k: path(k) for k in cols}


def summarize(item, colpaths=None):
    d = item["data"]
    m = ARXIV_RE.search(" ".join(str(d.get(f, "")) for f in ("extra", "url", "DOI", "archiveID", "number")))
    colpaths = colpaths if colpaths is not None else collection_paths()
    return {
        "key": d["key"], "title": d.get("title", ""), "date": d.get("date", ""),
        "authors": [c.get("lastName") or c.get("name", "") for c in d.get("creators", [])],
        "arxiv": m.group(1) if m else None, "url": d.get("url", ""),
        "collections": sorted(colpaths.get(k, k) for k in d.get("collections", [])),
        "tags": [t["tag"] for t in d.get("tags", [])],
        "zotero_link": f"zotero://select/library/items/{d['key']}",
    }


def _top(item):
    d = item["data"]
    if d.get("parentItem"):
        return api("GET", f"/items/{d['parentItem']}")
    return item


def find(query):
    q = query.strip()
    m = re.search(r"Zotero/storage/([A-Z0-9]{8})/", q)
    if m or re.fullmatch(r"[A-Z0-9]{8}", q):
        return [summarize(_top(api("GET", f"/items/{m.group(1) if m else q}")))]
    a = ARXIV_RE.fullmatch(q) or re.search(r"arxiv\.org/(?:abs|pdf)/" + ARXIV_RE.pattern, q)
    if a:
        q = a.group(1)
    if q.lower().endswith(".pdf"):  # PDF outside Zotero: search by file name words
        q = Path(q).stem
    hits = api("GET", "/items/top?" + urllib.parse.urlencode({"q": q, "qmode": "everything", "limit": 10}))
    colpaths = collection_paths()
    res = [summarize(h, colpaths) for h in hits if h["data"]["itemType"] not in ("attachment", "note")]
    if a:  # an arXiv id must match exactly; quick search often misses ids, so retry by title
        res = [r for r in res if r["arxiv"] == q]
        if not res:
            title = " ".join(_arxiv_entry(q).find("{http://www.w3.org/2005/Atom}title").text.split())
            hits = api("GET", "/items/top?" + urllib.parse.urlencode({"q": title[:80], "limit": 10}))
            res = [summarize(h, colpaths) for h in hits if h["data"]["itemType"] not in ("attachment", "note")]
            res = [r for r in res if r["arxiv"] == q or r["title"].lower() == title.lower()]
    return res


def _arxiv_entry(aid):
    with urllib.request.urlopen(f"http://export.arxiv.org/api/query?id_list={aid}", timeout=30) as r:
        root = ET.fromstring(r.read())
    return root.find("{http://www.w3.org/2005/Atom}entry")


def add_arxiv(aid):
    aid = ARXIV_RE.search(aid).group(1)
    existing = [r for r in find(aid) if r["arxiv"] == aid]
    if existing:
        return existing[0] | {"created": False}
    ns = {"a": "http://www.w3.org/2005/Atom"}
    e = _arxiv_entry(aid)
    names = [n.text.strip() for n in e.findall("a:author/a:name", ns)]
    item = {
        "itemType": "preprint",
        "title": " ".join(e.find("a:title", ns).text.split()),
        "abstractNote": " ".join(e.find("a:summary", ns).text.split()),
        "creators": [{"creatorType": "author", "firstName": " ".join(n.split()[:-1]), "lastName": n.split()[-1]}
                     for n in names],
        "date": e.find("a:published", ns).text[:10],
        "url": f"https://arxiv.org/abs/{aid}", "repository": "arXiv", "archiveID": f"arXiv:{aid}",
        "DOI": f"10.48550/arXiv.{aid}", "extra": f"arXiv:{aid}",
    }
    r = api("POST", "/items", [item])
    key = r["successful"]["0"]["key"]
    return summarize(api("GET", f"/items/{key}")) | {"created": True}


def link(key, video):
    video = str(Path(video).resolve())
    parent = api("GET", f"/items/{key}")
    children = api("GET", f"/items/{key}/children")
    old = [c for c in children if c["data"].get("title") == VIDEO_TITLE]
    if old:
        c = old[0]
        api("PATCH", f"/items/{c['key']}", {"path": video, "linkMode": "linked_file"},
            {"If-Unmodified-Since-Version": str(c["version"])})
        att = c["key"]
    else:
        r = api("POST", "/items", [{"itemType": "attachment", "linkMode": "linked_file", "parentItem": key,
                                    "title": VIDEO_TITLE, "path": video, "contentType": "video/mp4",
                                    "tags": [], "relations": {}, "note": "", "accessDate": "", "charset": ""}])
        if not r["successful"]:
            raise SystemExit(f"Zotero refused the attachment: {r['failed']}")
        att = r["successful"]["0"]["key"]
    tags = [t for t in parent["data"].get("tags", []) if t["tag"] != QUEUE_TAG]
    if not any(t["tag"] == VIDEO_TAG for t in tags):
        tags.append({"tag": VIDEO_TAG})
    if tags != parent["data"].get("tags", []):
        api("PATCH", f"/items/{key}", {"tags": tags}, {"If-Unmodified-Since-Version": str(parent["version"])})
    return {"key": key, "attachment": att, "path": video}


def queue():
    colpaths = collection_paths()
    return [summarize(i, colpaths) for i in _all(f"/items/top?tag={urllib.parse.quote(QUEUE_TAG)}")]


def ensure_search():
    for s in api("GET", "/searches"):
        if s["data"]["name"] == SEARCH_NAME:
            return {"search": s["key"], "created": False}
    r = api("POST", "/searches", [{"name": SEARCH_NAME,
                                   "conditions": [{"condition": "tag", "operator": "is", "value": VIDEO_TAG}]}])
    return {"search": r["successful"]["0"]["key"], "created": True}


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    fn = {"find": lambda: find(" ".join(args)), "add-arxiv": lambda: add_arxiv(args[0]),
          "link": lambda: link(args[0], args[1]), "queue": queue, "ensure-search": ensure_search}[cmd]
    print(json.dumps(fn(), indent=1, ensure_ascii=False))
