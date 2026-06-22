# -*- coding: utf-8 -*-
"""CPSC 召回：SaferProducts REST API（JSON）。无需 key。按品类关键词过滤。"""
from datetime import date, timedelta
from .base import Item, fetch_json, C_RECALL

API = "https://www.saferproducts.gov/RestWebServices/Recall"


def collect(cfg):
    cc = cfg.get("cpsc", {})
    look = int(cc.get("lookback_days", 7))
    since = (date.today() - timedelta(days=look)).isoformat()
    url = API + "?format=json&RecallDateStart=" + since
    try:
        data = fetch_json(url)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    kws = [k.lower() for k in cc.get("keywords", [])]
    items = []
    for rec in data:
        title = rec.get("Title", "") or ""
        prods = rec.get("Products", []) or []
        pnames = "; ".join((p.get("Name") or "") for p in prods)
        desc = rec.get("Description", "") or ""
        hay = (title + " " + pnames + " " + desc).lower()
        if kws and not any(k in hay for k in kws):
            continue
        u = rec.get("URL") or ""
        if isinstance(u, list):
            u = u[0] if u else ""
        items.append(Item(C_RECALL, title, "CPSC", u,
                          (rec.get("RecallDate") or "")[:10],
                          (pnames or desc)[:240]))
    return items
