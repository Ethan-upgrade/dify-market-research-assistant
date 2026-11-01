"""抓取层：一条「自动降级」的取页流水线。

背景：`urllib` 直接抓会被大量站点按 TLS 指纹/UA 识别拦掉（403/412），
导致「来源链接体检」里一堆「无法判断」。解决办法不是硬刚，而是换引擎重试。

引擎链（`auto` 模式）：
    1. urllib        零依赖，最快，能拿到就不折腾
    2. curl_cffi     伪造 Chrome 的 TLS 指纹（GitHub 6.8k★），专治「同样的 UA 但就是 403」
    3. playwright    真 Chrome 内核（GitHub 99k★），跑 JS、过简单挑战
    4. firecrawl     抓取服务（GitHub 198k★，需要 API Key 或自建地址），最重的兜底

前三层都是「装了就用、没装就跳过」，不引入硬依赖；firecrawl 需要显式配置。

用法：
    from mra.fetch import fetch_text
    r = fetch_text(url)           # {'ok','status','text','engine','reason'}
"""

from __future__ import annotations

import html
import io
import os
import re
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

BLOCK_CODES = {401, 403, 405, 412, 429, 503}


def is_pdf(url: str) -> bool:
    path = url.split("?")[0].lower()
    return path.endswith(".pdf") or ".pdf" in path


def _pdf_text(blob: bytes, max_pages: int = 40, max_chars: int = 400_000) -> dict:
    """PDF 抽文本：优先 PyMuPDF(11k★)，退回 pypdf(10.3k★)，都没有就明说。"""
    try:
        import pymupdf as fitz
    except Exception:
        try:
            import fitz                       # 旧包名
        except Exception:
            fitz = None
    if fitz is not None:
        try:
            doc = fitz.open(stream=blob, filetype="pdf")
            parts = [doc[i].get_text() for i in range(min(max_pages, doc.page_count))]
            text = "\n".join(parts)[:max_chars]
            doc.close()
            if text.strip():
                return {"ok": True, "text": text, "engine": "pymupdf", "reason": ""}
            return {"ok": False, "text": "", "engine": "pymupdf", "reason": "PDF 无可提取文本（可能是扫描件）"}
        except Exception as e:
            return {"ok": False, "text": "", "engine": "pymupdf", "reason": str(e)[:60]}

    try:
        import pypdf
    except Exception:
        return {"ok": False, "text": "", "engine": "none", "reason": "PDF 无法比对（未安装 pymupdf/pypdf）"}
    try:
        reader = pypdf.PdfReader(io.BytesIO(blob))
        parts = [pg.extract_text() or "" for pg in reader.pages[:max_pages]]
        text = "\n".join(parts)[:max_chars]
        if text.strip():
            return {"ok": True, "text": text, "engine": "pypdf", "reason": ""}
        return {"ok": False, "text": "", "engine": "pypdf", "reason": "PDF 无可提取文本（可能是扫描件）"}
    except Exception as e:
        return {"ok": False, "text": "", "engine": "pypdf", "reason": str(e)[:60]}


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw))


# ---------------------------------------------------------------- 各引擎
def _via_urllib(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*",
                                               "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(3_000_000)
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "pdf" in ctype or is_pdf(url) or raw[:4] == b"%PDF":
                got = _pdf_text(raw)
                return {"ok": got["ok"], "status": r.status, "text": got["text"],
                        "engine": got["engine"] + "(pdf)", "reason": got["reason"]}
            return {"ok": True, "status": r.status, "text": strip_html(raw.decode("utf-8", "ignore")),
                    "engine": "urllib", "reason": ""}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "text": "", "engine": "urllib", "reason": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "status": 0, "text": "", "engine": "urllib", "reason": str(e)[:60]}


def _via_curl_cffi(url: str, timeout: int) -> dict:
    try:
        from curl_cffi import requests as creq
    except Exception:
        return {"ok": False, "status": 0, "text": "", "engine": "curl_cffi", "reason": "未安装"}
    try:
        r = creq.get(url, impersonate="chrome", timeout=timeout,
                     headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        ctype = (r.headers.get("content-type") or "").lower()
        if "pdf" in ctype or is_pdf(url) or (r.content or b"")[:4] == b"%PDF":
            got = _pdf_text(r.content or b"")
            return {"ok": got["ok"], "status": r.status_code, "text": got["text"],
                    "engine": got["engine"] + "(pdf)", "reason": got["reason"]}
        body = r.text or ""
        if r.status_code >= 400:
            return {"ok": False, "status": r.status_code, "text": "", "engine": "curl_cffi",
                    "reason": f"HTTP {r.status_code}"}
        return {"ok": True, "status": r.status_code, "text": strip_html(body),
                "engine": "curl_cffi", "reason": ""}
    except Exception as e:
        return {"ok": False, "status": 0, "text": "", "engine": "curl_cffi", "reason": str(e)[:60]}


def _chrome_path() -> str:
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/usr/bin/google-chrome"):
        if os.path.exists(p):
            return p
    return ""


def _via_playwright(url: str, timeout: int) -> dict:
    if is_pdf(url):
        base = _via_urllib(url, timeout)
        if base["ok"]:
            return base
        return {"ok": False, "status": 0, "text": "", "engine": "playwright",
                "reason": base["reason"] or "PDF 无法比对"}
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {"ok": False, "status": 0, "text": "", "engine": "playwright", "reason": "未安装"}
    try:
        with sync_playwright() as p:
            kwargs = {"headless": True}
            exe = _chrome_path()
            if exe:
                kwargs["executable_path"] = exe
            b = p.chromium.launch(**kwargs)
            ctx = b.new_context(locale="zh-CN", viewport={"width": 1366, "height": 900})
            pg = ctx.new_page()
            r = pg.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            pg.wait_for_timeout(1500)
            txt = pg.inner_text("body")
            status = r.status if r else 0
            b.close()
            if status >= 400 and "验证" in txt[:200]:
                return {"ok": False, "status": status, "text": "", "engine": "playwright",
                        "reason": f"HTTP {status} 安全验证"}
            return {"ok": True, "status": status or 200, "text": strip_html(txt),
                    "engine": "playwright", "reason": ""}
    except Exception as e:
        return {"ok": False, "status": 0, "text": "", "engine": "playwright", "reason": str(e)[:60]}


def _via_firecrawl(url: str, timeout: int) -> dict:
    """Firecrawl（GitHub 198k★）：需要 FIRECRAWL_API_KEY，或自建 FIRECRAWL_API_URL。"""
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    base = os.environ.get("FIRECRAWL_API_URL", "https://api.firecrawl.dev").rstrip("/")
    if not key and "127.0.0.1" not in base and "localhost" not in base:
        return {"ok": False, "status": 0, "text": "", "engine": "firecrawl", "reason": "未配置 Key"}
    import json as _json
    payload = _json.dumps({"url": url, "formats": ["markdown"], "onlyMainContent": True}).encode()
    req = urllib.request.Request(base + "/v1/scrape", data=payload, method="POST",
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + key} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=max(timeout, 40)) as r:
            d = _json.loads(r.read().decode("utf-8", "ignore"))
        md = ((d.get("data") or {}).get("markdown") or "")
        if not md:
            return {"ok": False, "status": 0, "text": "", "engine": "firecrawl", "reason": "返回空内容"}
        return {"ok": True, "status": 200, "text": strip_html(md), "engine": "firecrawl", "reason": ""}
    except Exception as e:
        return {"ok": False, "status": 0, "text": "", "engine": "firecrawl", "reason": str(e)[:60]}


_ENGINES = {
    "urllib": _via_urllib,
    "curl_cffi": _via_curl_cffi,
    "playwright": _via_playwright,
    "firecrawl": _via_firecrawl,
}

AUTO_CHAIN = ["urllib", "curl_cffi", "playwright", "firecrawl"]


def fetch_text(url: str, timeout: int = 15, fetcher: str = "auto") -> dict:
    """按 fetcher 策略取页面纯文本。auto = 依次降级，拿到就停。"""
    chain = AUTO_CHAIN if fetcher in ("auto", "", None) else [fetcher]
    results = []
    for name in chain:
        fn = _ENGINES.get(name)
        if not fn:
            continue
        r = fn(url, timeout)
        r["engine"] = name
        if r["ok"]:
            return r
        results.append(r)
        # 明确的「页面不存在」不用再换引擎折腾
        if r["status"] in (404, 410):
            return r

    if not results:
        return {"ok": False, "status": 0, "text": "", "engine": "none", "reason": "无可用引擎"}

    # 归因优先：被反爬（403/412…）比「未安装/未配置」更能解释失败
    for r in results:
        if r["status"] in BLOCK_CODES:
            return r
    for r in results:
        if r["status"] in (404, 410):
            return r
    # 否则取第一个真正尝试过网络的（跳过 未安装/未配置）
    for r in results:
        if r["reason"] not in ("未安装", "未配置 Key"):
            return r
    return results[-1]
