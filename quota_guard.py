#!/usr/bin/env python3
"""
GitHub Quota Guard — 零依赖 GitHub API 客户端，自动处理 403 配额耗尽。

用法:
    from quota_guard import GitHubClient
    client = GitHubClient(tokens=["ghp_xxx", None])
    data = client.get("/repos/owner/repo")
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
CACHE_TTL = 300  # 5 分钟


class GitHubClient:
    def __init__(self, tokens=None, cache_ttl=CACHE_TTL, max_wait=600):
        self.tokens = tokens or [None]
        self.idx = 0
        self.cache = {}          # key -> (timestamp, data)
        self.cache_ttl = cache_ttl
        self.max_wait = max_wait
        self.remaining = {}
        self.calls = 0

    def _headers(self):
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-quota-guard/1.0",
        }
        tok = self.tokens[self.idx]
        if tok:
            h["Authorization"] = "Bearer " + tok
        return h

    def _switch(self):
        """切到下一个 token，返回是否切换成功。"""
        old = self.idx
        self.idx = (self.idx + 1) % len(self.tokens)
        return self.idx != old or len(self.tokens) > 1

    def _wait_for_reset(self, resp_headers):
        reset = resp_headers.get("X-RateLimit-Reset")
        if not reset:
            return False
        try:
            target = int(reset)
            wait = target - int(time.time()) + 2
        except (ValueError, TypeError):
            return False
        if wait <= 0 or wait > self.max_wait:
            return False
        print(f"[guard] 配额耗尽，等待 {wait}s 后重置...", flush=True)
        time.sleep(wait)
        return True

    def get(self, path, use_cache=True):
        """GET 请求，自动处理配额。返回解析后的 JSON。"""
        key = path
        if use_cache and key in self.cache:
            ts, data = self.cache[key]
            if time.time() - ts < self.cache_ttl:
                return data

        attempts = 0
        while attempts < len(self.tokens) * 2 + 2:
            attempts += 1
            req = urllib.request.Request(API + path, headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self.remaining[self.idx] = int(resp.headers.get("X-RateLimit-Remaining", -1))
                    self.cache[key] = (time.time(), data)
                    self.calls += 1
                    return data
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")[:200]
                if e.code in (403, 429):
                    self.remaining[self.idx] = 0
                    # 先试切 token（最快）
                    if self._switch():
                        continue
                    # 只有一个 token：等重置
                    if self._wait_for_reset(e.headers):
                        continue
                    raise RuntimeError(f"GitHub 配额耗尽且无法等待: {body}")
                raise RuntimeError(f"HTTP {e.code}: {body}")
            except Exception as e:
                raise RuntimeError(f"请求失败: {type(e).__name__}: {e}")
        raise RuntimeError("超过最大重试次数")

    def status(self):
        """查询所有 token 的配额状态。"""
        out = []
        for i, tok in enumerate(self.tokens):
            old = self.idx
            self.idx = i
            try:
                req = urllib.request.Request(API + "/rate_limit", headers=self._headers())
                with urllib.request.urlopen(req, timeout=15) as resp:
                    d = json.loads(resp.read().decode("utf-8"))["resources"]["core"]
                    out.append({
                        "token": f"token#{i}" if tok else "anonymous",
                        "limit": d["limit"], "remaining": d["remaining"],
                        "reset_in": max(0, d["reset"] - int(time.time())),
                    })
            except Exception as e:
                out.append({"token": f"token#{i}", "error": str(e)[:80]})
            finally:
                self.idx = old
        return out


def main():
    ap = argparse.ArgumentParser(description="GitHub Quota Guard")
    ap.add_argument("--status", action="store_true", help="显示所有 token 的配额")
    ap.add_argument("--repos", help="逗号分隔的 owner/repo 列表")
    ap.add_argument("--tokens", help="逗号分隔的 token（留空则用匿名）")
    args = ap.parse_args()

    tokens = [t for t in (args.tokens or "").split(",") if t] or [None]
    client = GitHubClient(tokens=tokens)

    if args.status:
        print(json.dumps(client.status(), indent=2, ensure_ascii=False))
        return
    if args.repos:
        for full in args.repos.split(","):
            full = full.strip()
            if not full:
                continue
            try:
                d = client.get("/repos/" + full)
                print(f"{d['full_name']:<42} ★{d['stargazers_count']:<6} {d.get('language')}")
            except Exception as e:
                print(f"{full:<42} ERROR: {e}")
        print(f"\n请求数 {client.calls}，缓存条目 {len(client.cache)}")
        return
    ap.print_help()


if __name__ == "__main__":
    main()
