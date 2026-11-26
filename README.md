# GitHub Quota Guard / GitHub 配额守护

<p align="center"><b>再也不会因为 403 rate limit 中断 GitHub API 任务。</b></p>

## 痛点

写 GitHub 脚本的人都会遇到：

```
HTTP 403: API rate limit exceeded for 60 requests/hour
```

未认证只有 60 次/小时。搜索 API 更少（10 次/分钟）。
一个稍微大点的脚本——比如采集 30 个项目的详情、逐个核实 star——配额一下就吃光了。

常见"解决"方案：

- 等一小时 → 任务黄了
- 买 GitHub Copilot → 不是为了 API 配额
- 手写一堆 token 轮换代码 → 每个项目重复造轮子

## 解决

`github-quota-guard` 提供一个零依赖包装器：

- ✅ **自动检测** 403 rate limit 和 secondary rate limit
- ✅ **多个 token 轮换**：一个限额了自动切下一个
- ✅ **精确等待**：读取 `X-RateLimit-Reset` 头，等到重置那一刻再继续，不多等一秒
- ✅ **请求预算**：提前估算还够几次调用，不够就主动停
- ✅ **缓存**：重复请求直接返回缓存结果，不浪费配额
- ✅ **零依赖**：Python 标准库，单文件可用

## 快速开始

```python
from quota_guard import GitHubClient

# 支持多个 token，自动轮换
client = GitHubClient(tokens=[
    "ghp_xxx1",
    "ghp_xxx2",
    None,  # None = 未认证请求，作为最后兜底
])

# 像普通 requests 一样用
data = client.get("/repos/xhchy/renhua")
print(data["stargazers_count"])

# 查看配额状态
print(client.status())  # {'remaining': 4231, 'limit': 5000, 'reset_in': 1842}
```

```bash
# 命令行：看当前配额
python quota_guard.py --status

# 命令行：批量取仓库信息（自动省配额）
python quota_guard.py --repos xhchy/renhua,everyday-e scratching/...
```

## 它怎么省配额

| 策略 | 效果 |
|---|---|
| 本地缓存（默认 5 分钟） | 重复请求 0 消耗 |
| ETag 条件请求 | 未变更返回 304，不计入主配额 |
| 多 token 轮换 | 可用额度 × token 数量 |
| 精确等待重置 | 不盲目 sleep |
| 批量预检 | 调用前先算够不够，不够提前报 |

## 鉴权方式

只支持 Personal Access Token（Classic 或 Fine-grained）。
**不收集、不上传任何 token**——全部在本地内存里，代码开源可审计。

## 为什么不用 PyGithub / gh CLI

它们很好，但：
- PyGithub 要 pip install，很多场景不方便
- gh CLI 要登录，且不好嵌进脚本
- 都不做多 token 轮换和预算控制

这个库就一件事：**在配额紧张时，让你的脚本继续跑完。**

## 许可

MIT
