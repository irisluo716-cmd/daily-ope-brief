#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成稿合成器（模型 A 生成 → AI 评审 → REJECT 反馈重写 ≤3 次 → 只有 PASS 才发布）。

- 日期由代码动态注入两段 Prompt（强制 AI 用今天的精确日期判断时效、写页眉）。
- 通过后：渲染 CI HTML → 写当日存档 briefs/<date>.html、当日端口 briefs/latest.html、
  重建存档索引 briefs/index.html（往日按天累积，端口只显示当天）。
- 三次仍未过：不发布成稿，写 review-failed 标记，退出 0（原始素材仍保留）。
调用 MiniMax（OpenAI 兼容 /chat/completions）；密钥读环境变量 MINIMAX_API_KEY，仅 stdlib，无第三方 SDK。"""
import os
import sys
import re
import json
import datetime
import urllib.request
import urllib.error

import yaml
import render
import notify

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "briefs", "raw")
OUT_DIR = os.path.join(HERE, "briefs")

# 成稿栏目（与 render.SECTION_ORDER 对齐）
SECTION_KEYS = ["company", "product", "weather", "review", "policy"]


# ---------------- 模型调用（MiniMax OpenAI 兼容接口；唯一外呼处，便于打桩测试）----------------
def call_model(role_cfg, system, user):
    """role_cfg: {base_url, api_key_env, model, max_tokens, temperature, timeout}。返回模型输出纯文本。"""
    key_env = role_cfg.get("api_key_env", "MINIMAX_API_KEY")
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise RuntimeError("缺少 MiniMax API key（环境变量 %s）" % key_env)
    url = role_cfg.get("base_url", "https://api.minimaxi.com/v1").rstrip("/") + "/chat/completions"
    body = {
        "model": role_cfg.get("model", "MiniMax-M2"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": int(role_cfg.get("max_tokens", 16000)),
    }
    if role_cfg.get("temperature") is not None:
        body["temperature"] = float(role_cfg["temperature"])
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=int(role_cfg.get("timeout", 300))) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError("MiniMax HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
    br = resp.get("base_resp") or {}
    if br and br.get("status_code") not in (0, None):
        raise RuntimeError("MiniMax base_resp %s: %s" % (br.get("status_code"), br.get("status_msg")))
    choices = resp.get("choices") or []
    if not choices:
        raise RuntimeError("MiniMax 无 choices：%s" % str(resp)[:300])
    content = (choices[0].get("message") or {}).get("content", "") or ""
    # MiniMax M 系列是推理模型，content 里会带 <think>…</think>，剥掉只留正文
    content = re.sub(r"(?s)<think>.*?</think>\s*", "", content).strip()
    return content


def _parse_json(text):
    """从模型输出里抠出 JSON 对象。"""
    if not text:
        raise ValueError("空输出")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("未找到 JSON 对象")
    return json.loads(t[a:b + 1])


# ---------------- Prompt（日期由代码注入）----------------
def gen_prompt(today, cutoff, raw_items):
    system = (
        "你是隆鑫通用·产品策划部的资深通机行业分析师。把采集到的英文原始素材整理成一份"
        "面向中国读者的中文每日简报（北美·欧洲市场口径）。严格按要求输出 JSON，不要输出任何解释。\n"
        "硬规则：\n"
        "1) 每条都必须配 1–2 句中文「小结」(gist)，写清是什么、关键数字、为什么值得看——"
        "国内读者打不开原网站，必须靠小结读懂；不得编造原文之外的事实。\n"
        "2) 时效：今天是 %s。发布日期早于 %s 的条目一律剔除，不得当作新闻。\n"
        "3) 只保留与发电机/通用汽油发动机/割草机器人/水泵/微耕机/草坪车相关、且面向北美或欧洲市场的条目；"
        "剔除拍卖/备件电商/明显无关时政/非目标市场(印度/俄/乌/孟等)噪音。\n"
        "4) 归类到 5 个栏目 key：company(大公司动向)/product(新产品)/weather(灾害天气)/review(用户评论风向)/"
        "policy(关税·排放·召回)；同主题聚合成一条，去重、按重要性排序。\n"
        "5) 禁止出现推测标注式括号(如[推测…])；禁止任何 AI 痕迹或内部文档名/规则名；用中文。\n"
        "输出 JSON：{\"lede\":[\"3-4条今日速览\"],"
        "\"sections\":{\"company\":[{\"title\":\"\",\"gist\":\"\",\"source\":\"\",\"url\":\"\",\"date\":\"YYYY-MM-DD\"}],"
        "\"product\":[],\"weather\":[],\"review\":[],\"policy\":[]}}。"
        "policy 无新动作就给空数组。url 用素材里的原文链接。"
        % (today, cutoff)
    )
    user = "今天=%s。原始素材(JSON)：\n%s" % (today, json.dumps(raw_items, ensure_ascii=False))
    return system, user


def judge_prompt(today, cutoff, brief):
    system = (
        "你是严格的中文简报质检员(AI Judge)。对照规则审查给定的成稿 JSON，只输出 JSON。\n"
        "今天是 %s。逐条检查：\n"
        "A) 每个条目的 gist 非空、且是对标题的忠实展开(无明显编造)；\n"
        "B) 没有发布日期早于 %s 却被当作新闻的条目；\n"
        "C) 无推测标注式括号、无 AI 痕迹措辞、无内部文档/规则名；全中文；\n"
        "D) 条目与 6 类通机产品 + 北美/欧洲市场相关，噪音已剔除；\n"
        "E) lede 速览 3-4 条且与正文一致。\n"
        "全部满足输出 {\"verdict\":\"PASS\",\"issues\":[]}；否则 "
        "{\"verdict\":\"REJECT\",\"issues\":[\"具体、可执行的修改意见\",...]}。"
        % (today, cutoff)
    )
    user = "待审成稿(JSON)：\n%s" % json.dumps(brief, ensure_ascii=False)
    return system, user


def revise_user(prev_brief, issues, today, cutoff):
    return (
        "今天=%s；时效剔除线=%s。你上一版成稿被评审驳回，修改意见如下，请据此重写并只输出修正后的完整 JSON("
        "结构同前)：\n意见：\n- %s\n\n上一版：\n%s"
        % (today, cutoff, "\n- ".join(issues), json.dumps(prev_brief, ensure_ascii=False))
    )


# ---------------- 编排 ----------------
def build_metrics(raw):
    items = raw.get("items", [])
    from collections import Counter
    c = Counter(it.get("category", "") for it in items)
    return [
        {"label": "今日监测条目", "value": len(items)},
        {"label": "大公司动向", "value": c.get("大公司动向", 0)},
        {"label": "新品 / 评测", "value": "%d / %d" % (c.get("新产品", 0), c.get("用户评论风向", 0))},
        {"label": "天气预警", "value": c.get("灾害天气预警", 0), "hot": True},
    ]


def write_archive(today, html):
    os.makedirs(OUT_DIR, exist_ok=True)
    day_path = os.path.join(OUT_DIR, today + ".html")
    with open(day_path, "w", encoding="utf-8") as f:
        f.write(html)
    # 当日端口：只显示今天
    with open(os.path.join(OUT_DIR, "latest.html"), "w", encoding="utf-8") as f:
        f.write(html)
    rebuild_index()
    return day_path


def rebuild_index():
    days = []
    for fn in os.listdir(OUT_DIR):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\.html$", fn)
        if m:
            days.append(m.group(1))
    days.sort(reverse=True)
    lines = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>通机行业每日简报 · 存档</title>",
             '<style>body{font-family:"Microsoft YaHei",Calibri,sans-serif;max-width:720px;margin:24px auto;'
             'padding:0 16px;color:#2b2b2b}h1{font-size:20px;color:#595757;border-bottom:3px solid #E9470B;'
             'padding-bottom:8px}a{color:#1a1a1a;text-decoration:none}li{margin:8px 0;font-size:15px}'
             '.org{color:#595757;font-size:12px;margin-top:20px}</style></head><body>',
             "<h1>通机行业每日简报 · 存档</h1>",
             '<p style="font-size:13px;color:#8a8a87">最新一期见 <a href="latest.html">latest.html</a>。以下按日期累积：</p>',
             "<ul>"]
    for d in days:
        lines.append('<li><a href="%s.html">%s</a></li>' % (d, d))
    lines.append("</ul><div class='org'>隆鑫通用 · 产品策划部</div></body></html>")
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    cfg = yaml.safe_load(open(os.path.join(HERE, "sources.yaml"), encoding="utf-8"))
    sc = cfg.get("synthesis", {})
    site_url = os.environ.get("SITE_URL", sc.get("site_url", ""))
    today = datetime.date.today().isoformat()
    new_within = int(sc.get("new_within_days", 5))
    cutoff = (datetime.date.today() - datetime.timedelta(days=new_within)).isoformat()
    max_retries = int(sc.get("max_retries", 3))

    raw_path = os.path.join(RAW_DIR, today + ".json")
    if not os.path.exists(raw_path):
        print("无当日原始素材：%s，跳过合成。" % raw_path)
        return 0
    raw = json.load(open(raw_path, encoding="utf-8"))

    common = {"base_url": sc.get("base_url", "https://api.minimaxi.com/v1"),
              "api_key_env": sc.get("api_key_env", "MINIMAX_API_KEY")}

    def role_cfg(name, default_model):
        d = dict(common)
        d.update(sc.get("models", {}).get(name, {}))
        d.setdefault("model", default_model)
        return d

    gen_cfg = role_cfg("generator", "MiniMax-M2.7")
    judge_cfg = role_cfg("judge", "MiniMax-M2.5")

    # 第 1 次生成
    g_sys, g_user = gen_prompt(today, cutoff, raw.get("items", []))
    brief = None
    last_issues = []
    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            text = call_model(gen_cfg, g_sys, g_user)
        else:
            text = call_model(gen_cfg, g_sys, revise_user(brief, last_issues, today, cutoff))
        try:
            brief = _parse_json(text)
        except Exception as e:
            last_issues = ["上版输出不是合法 JSON（%r），请只输出规定结构的 JSON。" % e]
            print("第 %d 次生成：JSON 解析失败，反馈重写。" % attempt)
            continue

        j_sys, j_user = judge_prompt(today, cutoff, brief)
        try:
            verdict = _parse_json(call_model(judge_cfg, j_sys, j_user))
        except Exception as e:
            print("评审输出解析失败（%r），按 REJECT 处理。" % e)
            verdict = {"verdict": "REJECT", "issues": ["评审无法解析，请规范输出。"]}

        if str(verdict.get("verdict", "")).upper() == "PASS":
            print("第 %d 次：评审 PASS。" % attempt)
            break
        last_issues = verdict.get("issues", []) or ["未给出具体意见。"]
        print("第 %d 次：评审 REJECT —— %s" % (attempt, "；".join(last_issues)[:200]))
    else:
        # 循环正常结束（未 break）= 三次仍未 PASS
        marker = os.path.join(RAW_DIR, today + ".review-failed.txt")
        with open(marker, "w", encoding="utf-8") as f:
            f.write("AI 评审 %d 次未通过，未发布成稿。\n最后意见：\n- %s\n" % (max_retries, "\n- ".join(last_issues)))
        print("⚠️ %d 次评审均未通过，未发布成稿（原始素材已保留）。" % max_retries)
        notify.notify_failure("AI 评审 %d 次未通过，未发布今日成稿。最后意见：%s"
                              % (max_retries, "；".join(last_issues)[:400]))
        return 0

    # PASS → 渲染发布
    brief["date"] = today  # 强制页眉日期 = 今天（代码注入，不信任模型）
    brief.setdefault("metrics", build_metrics(raw))
    # 仅保留规定栏目
    secs = brief.get("sections", {})
    brief["sections"] = {k: secs.get(k, []) for k in SECTION_KEYS}
    html = render.render(brief)
    path = write_archive(today, html)
    print("已发布成稿：%s（+ latest.html + index.html）" % path)
    notify.notify_success(brief, site_url, os.path.join(OUT_DIR, "latest.html"))
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        notify.notify_failure("synthesize 运行异常：%r" % e)
        sys.exit(1)
    sys.exit(rc)
