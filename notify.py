# -*- coding: utf-8 -*-
"""飞书通知（自定义机器人 webhook）：成稿成功推卡片(速览+链接)，失败/异常推告警。
仅 stdlib。webhook 走环境变量 FEISHU_WEBHOOK，可选加签 FEISHU_SIGN_SECRET。
独立运行用于 workflow 的失败兜底：python notify.py "失败原因"。"""
import os
import sys
import json
import time
import hmac
import hashlib
import base64
import urllib.request


def _sign(secret, ts):
    s = ("%s\n%s" % (ts, secret)).encode("utf-8")
    return base64.b64encode(hmac.new(s, b"", hashlib.sha256).digest()).decode("utf-8")


def _post(payload, webhook="", secret=""):
    webhook = webhook or os.environ.get("FEISHU_WEBHOOK", "")
    secret = secret or os.environ.get("FEISHU_SIGN_SECRET", "")
    if not webhook:
        print("未配置 FEISHU_WEBHOOK，跳过飞书通知。")
        return False, "no-webhook"
    if secret:
        ts = str(int(time.time()))
        payload = dict(payload)
        payload["timestamp"] = ts
        payload["sign"] = _sign(secret, ts)
    req = urllib.request.Request(
        webhook, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        ok = (d.get("code") in (0, None)) and (d.get("StatusCode") in (0, None))
        return ok, str(d)[:200]
    except Exception as e:
        return False, repr(e)


def _card(title, template, md, button_url=""):
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": md}}]
    if button_url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "text": {"tag": "plain_text", "content": "查看完整简报"},
            "url": button_url, "type": "primary"}]})
    return {"msg_type": "interactive", "card": {
        "config": {"wide_screen_mode": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
        "elements": elements}}


def notify_success(brief, site_url="", webhook="", secret=""):
    date = brief.get("date", "")
    lede = brief.get("lede") or []
    md = "**北美 · 欧洲市场**\n\n" + "\n".join("• " + str(x) for x in lede[:5])
    if not site_url:
        md += "\n\n_（未配置站点链接，完整简报见仓库 briefs/latest.html）_"
    title = "通机行业每日简报 · %s" % date
    return _post(_card(title, "red", md, site_url), webhook, secret)


def notify_failure(text, webhook="", secret=""):
    return _post(_card("⚠️ 每日简报生成失败", "red", str(text)[:1000]), webhook, secret)


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "每日 workflow 运行失败。"
    ok, info = notify_failure(msg)
    print("飞书告警:", ok, info)
