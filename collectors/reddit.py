# -*- coding: utf-8 -*-
"""用户评论风向：Reddit 公开 RSS（无需 app / key）。
数据中心 IP 易被 429 限流 —— 带退避重试，仍失败则跳过并在产出里记一行说明。"""
import os
import time
import urllib.parse
from .base import Item, fetch, parse_feed, C_REVIEW


def _auth_feed(rc, ua):
    """认证 .rss?feed= feed（首页或自定义 multireddit）。URL 走环境变量 REDDIT_FEED_URL，
    数据中心 IP 也能 200（公开 .json 会被 403）。按 feed_keywords 过滤到通机相关。"""
    url = os.environ.get("REDDIT_FEED_URL", "").strip()
    if not url:
        return []
    kws = [k.lower() for k in rc.get("feed_keywords", [])]
    out = []
    try:
        rows = parse_feed(fetch(url, headers={"User-Agent": ua}, retries=3, backoff=3))
    except Exception:
        return out
    for e in rows:
        title = e["title"] or ""
        if kws and not any(k in title.lower() for k in kws):
            continue
        out.append(Item(C_REVIEW, title, "Reddit 认证feed", e["link"], (e["date"] or "")[:10], ""))
    return out


def collect(cfg):
    rc = cfg.get("reddit", {})
    ua = rc.get("user_agent", "daily-ope-brief/0.1 (contact iris)")
    per = int(rc.get("per_sub", 5))
    delay = float(rc.get("delay", 2))
    items = []
    skipped = []

    # 0) 认证 feed（最稳，覆盖你订阅 / 自定义 feed 里的通机版块）
    items += _auth_feed(rc, ua)

    for sub in rc.get("subreddits", []):
        url = "https://www.reddit.com/r/%s/top.rss?t=day" % sub
        try:
            rows = parse_feed(fetch(url, headers={"User-Agent": ua}, retries=3, backoff=3))[:per]
            if not rows:
                skipped.append(sub)
            for e in rows:
                items.append(Item(C_REVIEW, e["title"], "Reddit / r/" + sub,
                                  e["link"], (e["date"] or "")[:10], ""))
        except Exception:
            skipped.append(sub)
        time.sleep(delay)

    for q in rc.get("search_queries", []):
        url = "https://www.reddit.com/search.rss?sort=new&t=week&q=" + urllib.parse.quote(q)
        try:
            for e in parse_feed(fetch(url, headers={"User-Agent": ua}))[:5]:
                items.append(Item(C_REVIEW, e["title"], "Reddit 搜索: " + q,
                                  e["link"], (e["date"] or "")[:10], ""))
        except Exception:
            pass
        time.sleep(delay)

    if skipped:
        items.append(Item(C_REVIEW,
                          "（采集说明）以下子版块本次限流 / 无数据，已跳过：" + ", ".join(skipped),
                          "脚本日志", "", "",
                          "Reddit 对数据中心 IP 限流属正常，可按需手动 Browser MCP 补抓"))
    return items
