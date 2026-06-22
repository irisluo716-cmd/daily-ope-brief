#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通机行业每日素材采集器（只采集，不下结论）。
产出 briefs/raw/YYYY-MM-DD.md（人读）+ .json（备用）。成稿请据原始素材另写。"""
import os
import json
import datetime
import yaml

from collectors.base import CATEGORY_ORDER
from collectors import federal_register, cpsc, weather, news_rss, youtube, reddit

HERE = os.path.dirname(os.path.abspath(__file__))

COLLECTORS = [
    ("Federal Register（关税+排放）", federal_register),
    ("CPSC 召回", cpsc),
    ("天气预警", weather),
    ("新闻 RSS（公司+新品）", news_rss),
    ("YouTube 评测", youtube),
    ("Reddit 风向", reddit),
]


def load_cfg():
    with open(os.path.join(HERE, "sources.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    cfg = load_cfg()
    all_items = []
    log = []
    for name, mod in COLLECTORS:
        try:
            got = mod.collect(cfg)
            all_items.extend(got)
            log.append("%s：%d 条" % (name, len(got)))
        except Exception as e:
            log.append("%s：错误 %r" % (name, e))
        print(log[-1])

    # 去重（按 url；无 url 的说明行保留）
    seen = set()
    uniq = []
    for it in all_items:
        k = it.key()
        if not k:
            uniq.append(it)
            continue
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)

    groups = {}
    for c in CATEGORY_ORDER:
        groups[c] = []
    for it in uniq:
        groups.setdefault(it.category, []).append(it)

    today = datetime.date.today().isoformat()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    outdir = os.path.join(HERE, "briefs", "raw")
    os.makedirs(outdir, exist_ok=True)

    lines = []
    lines.append("# 通机行业每日素材 · %s" % today)
    lines.append("")
    lines.append("> 脚本自动采集的**原始素材**，未经判断、排序、推测标注。成稿请据此另写。")
    lines.append("> 采集时间：%s" % now)
    lines.append("")
    for c in CATEGORY_ORDER:
        rows = groups.get(c, [])
        lines.append("## %s (%d)" % (c, len(rows)))
        if not rows:
            lines.append("- （今日无采集到条目）")
        for it in rows:
            meta = " — ".join([x for x in [it.source, it.date] if x])
            head = "- **%s**" % it.title
            if meta:
                head += " — %s" % meta
            lines.append(head)
            if it.url:
                lines.append("  %s" % it.url)
            if it.summary:
                lines.append("  > %s" % it.summary)
        lines.append("")
    lines.append("---")
    lines.append("## 采集日志")
    for entry in log:
        lines.append("- %s" % entry)
    lines.append("- 去重后总条目：%d" % len(uniq))

    md_path = os.path.join(outdir, today + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(os.path.join(outdir, today + ".json"), "w", encoding="utf-8") as f:
        json.dump({"date": today, "collected_at": now, "log": log,
                   "items": [it.to_dict() for it in uniq]},
                  f, ensure_ascii=False, indent=2)

    print("\n写出：%s（去重后 %d 条）" % (md_path, len(uniq)))


if __name__ == "__main__":
    main()
