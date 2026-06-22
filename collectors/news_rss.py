# -*- coding: utf-8 -*-
"""大公司动向 + 新产品：Google News RSS（按品牌 / 主题，无需 key）+ 行业媒体 RSS（尽力，失败跳过）。
Google News 噪音大（generator 误中 AI/量子、Honda engine 误中 F1、launch 误中枪击等），
故对 Google News 结果做 白名单(require_any) + 黑名单(exclude_any) 标题过滤；
行业媒体 RSS 已是垂直来源，只过黑名单、不过白名单。"""
import urllib.parse
from .base import Item, fetch, parse_feed, C_COMPANY, C_PRODUCT

GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="


def _src_from_title(t):
    # Google News 标题格式："Headline - Source"
    if " - " in t:
        head, src = t.rsplit(" - ", 1)
        return head.strip(), src.strip()
    return t, "Google News"


def _ok(title, require, exclude):
    t = (title or "").lower()
    if exclude and any(x in t for x in exclude):
        return False
    if require and not any(x in t for x in require):
        return False
    return True


def _gn(query, category, limit, require, exclude, bad_src):
    items = []
    try:
        rows = parse_feed(fetch(GN + urllib.parse.quote(query)))[:limit]
    except Exception:
        return items
    for e in rows:
        head, src = _src_from_title(e["title"])
        if not _ok(head, require, exclude):
            continue
        if bad_src and any(b in src.lower() for b in bad_src):
            continue
        items.append(Item(category, head, src, e["link"], (e["date"] or "")[:16], ""))
    return items


def collect(cfg):
    nc = cfg.get("news", {})
    limit = int(nc.get("per_query", 10))
    require = [x.lower() for x in nc.get("require_any", [])]
    exclude = [x.lower() for x in nc.get("exclude_any", [])]
    bad_src = [x.lower() for x in nc.get("exclude_sources", [])]
    items = []
    for q in nc.get("company_queries", []):
        items += _gn(q, C_COMPANY, limit, require, exclude, bad_src)
    for q in nc.get("product_queries", []):
        items += _gn(q, C_PRODUCT, limit, require, exclude, bad_src)
    for feed in nc.get("media_feeds", []):
        try:
            rows = parse_feed(fetch(feed["url"]))[:int(feed.get("limit", 6))]
        except Exception:
            continue
        for e in rows:
            if not _ok(e["title"], None, exclude):   # 垂直媒体只过黑名单
                continue
            items.append(Item(C_COMPANY, e["title"], feed.get("name", "行业媒体"),
                              e["link"], (e["date"] or "")[:16], (e["summary"] or "")[:200]))
    return items
