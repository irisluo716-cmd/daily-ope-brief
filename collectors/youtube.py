# -*- coding: utf-8 -*-
"""用户评论风向（评测 / 口碑）：YouTube Data API v3 search。
key 优先读环境变量 YOUTUBE_API_KEY（GitHub Actions Secrets），其次读 sources.yaml。"""
import os
import urllib.parse
from datetime import datetime, timedelta
from .base import Item, fetch_json, C_REVIEW

SEARCH = "https://www.googleapis.com/youtube/v3/search"


def collect(cfg):
    yc = cfg.get("youtube", {})
    key = os.environ.get("YOUTUBE_API_KEY") or yc.get("api_key", "")
    if not key:
        return []
    look = int(yc.get("lookback_days", 7))
    since = (datetime.utcnow() - timedelta(days=look)).strftime("%Y-%m-%dT%H:%M:%SZ")
    max_results = str(int(yc.get("max_results", 6)))
    items = []
    for q in yc.get("queries", []):
        params = {"part": "snippet", "q": q, "type": "video", "order": "date",
                  "maxResults": max_results, "publishedAfter": since,
                  "relevanceLanguage": "en", "key": key}
        try:
            data = fetch_json(SEARCH + "?" + urllib.parse.urlencode(params))
        except Exception:
            continue
        for it in data.get("items", []) or []:
            vid = (it.get("id") or {}).get("videoId")
            if not vid:
                continue
            s = it.get("snippet", {}) or {}
            items.append(Item(C_REVIEW, s.get("title", ""),
                              "YouTube / " + s.get("channelTitle", ""),
                              "https://youtu.be/" + vid,
                              (s.get("publishedAt") or "")[:10],
                              (s.get("description") or "")[:160]))
    return items
