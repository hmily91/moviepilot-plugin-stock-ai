# -*- coding: utf-8 -*-
"""
push_to_github.py —— 将「股票AI分析助手」插件自动发布到 GitHub 公开仓库
======================================================================

功能：
    1. 使用 GitHub Personal Access Token 调用 REST API 创建公开仓库
       （仓库已存在则自动识别并复用）。
    2. 在当前目录（即插件目录）初始化 git 仓库并提交全部文件。
    3. 推送到仓库的 main 分支。

安全设计（重要）：
    - 本脚本【不】把 Token 明文写死在文件中，而是从环境变量 GITHUB_TOKEN 读取，
      避免 Token 随公开仓库泄露到 GitHub 上。
    - 运行前请先设置环境变量：
        Windows： set GITHUB_TOKEN=ghp_你的Token
        Linux/macOS： export GITHUB_TOKEN=ghp_你的Token
    - 该 Token 需具备 repo 权限（用于创建仓库与推送）。

依赖：仅使用 Python 标准库（urllib / subprocess / json / os / sys），无需额外安装。
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# ------------------------- 可配置常量 ------------------------- #
REPO_NAME = "moviepilot-plugin-stock-ai"
REPO_DESC = "MoviePilot V3 插件：股票AI分析助手（A股行情 + LLM 智能分析 + 定时推送）"
API_BASE = "https://api.github.com"
BRANCH = "main"
# 提交使用的身份（仅本地 git 配置，不会作为作者公开泄露凭据）
GIT_USER_NAME = "StockAi Plugin"
GIT_USER_EMAIL = "stock-ai-plugin@users.noreply.github.com"


# ------------------------- 基础工具 ------------------------- #
def get_token() -> str:
    """从环境变量读取 GitHub Token，缺失则报错退出。"""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("错误：未检测到 GITHUB_TOKEN 环境变量。")
        print("请先设置后再运行：")
        print("  Windows : set GITHUB_TOKEN=ghp_你的Token")
        print("  macOS/Linux: export GITHUB_TOKEN=ghp_你的Token")
        sys.exit(1)
    return token


def api_request(method: str, url: str, token: str, data: dict = None):
    """发起 GitHub REST API 请求，返回 (status_code, body)。"""
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.getcode(), json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if hasattr(e, "read") else ""
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def get_login(token: str) -> str:
    """获取当前 Token 对应的 GitHub 用户名。"""
    code, resp = api_request("GET", f"{API_BASE}/user", token)
    if code == 200 and isinstance(resp, dict):
        login = resp.get("login")
        if login:
            return login
    print(f"错误：获取 GitHub 用户信息失败（HTTP {code}）：{resp}")
    sys.exit(1)


def create_repo(token: str, login: str) -> str:
    """
    创建公开仓库；若已存在（HTTP 422）则复用。
    返回仓库全名（owner/repo）。
    """
    url = f"{API_BASE}/user/repos"
    payload = {
        "name": REPO_NAME,
        "description": REPO_DESC,
        "private": False,          # 公开仓库
        "auto_init": False,        # 不自动初始化，避免与本地提交冲突
        "has_issues": True,
        "has_readme": False,
    }
    code, resp = api_request("POST", url, token, payload)
    if code == 201 and isinstance(resp, dict):
        print(f"✅ 已创建公开仓库：{resp.get('html_url')}")
        return resp.get("full_name")
    if code == 422:
        # 名称冲突通常代表仓库已存在
        full = f"{login}/{REPO_NAME}"
        print(f"ℹ️ 仓库可能已存在，直接使用：{full}")
        return full
    print(f"错误：创建仓库失败（HTTP {code}）：{resp}")
    sys.exit(1)


def run_git(args: list, cwd: str) -> bool:
    """执行 git 命令，返回是否成功。"""
    try:
        res = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        print("错误：未检测到 git，请先安装 Git 并加入 PATH。")
        sys.exit(1)
    if res.returncode != 0:
        if res.stderr.strip():
            print(f"⚠️ git {' '.join(args)} 出错：{res.stderr.strip()}")
        return False
    if res.stdout.strip():
        print(res.stdout.strip())
    return True


# ------------------------- 主流程 ------------------------- #
def main() -> None:
    token = get_token()
    here = os.path.dirname(os.path.abspath(__file__))
    print(f"📁 插件目录：{here}")

    login = get_login(token)
    full_name = create_repo(token, login)

    # 初始化本地 git 仓库（若尚未初始化）
    if not os.path.exists(os.path.join(here, ".git")):
        if not run_git(["init", "-b", BRANCH], here):
            print("错误：git init 失败。")
            sys.exit(1)
    else:
        print("ℹ️ 已存在 .git，跳过初始化")
        # 确保分支名为 main
        run_git(["checkout", "-B", BRANCH], here)

    run_git(["config", "user.email", GIT_USER_EMAIL], here)
    run_git(["config", "user.name", GIT_USER_NAME], here)
    run_git(["add", "-A"], here)
    # 仅在存在变更时提交，避免空提交报错
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=here, capture_output=True, text=True, check=False
    )
    if status.stdout.strip():
        run_git(["commit", "-m", "feat: 初始化股票AI分析助手 MoviePilot V3 插件"], here)
    else:
        print("ℹ️ 没有需要提交的变更")

    # 设置远程（使用 Token 鉴权，Token 仅存于本地 .git/config，不会进入提交）
    run_git(["remote", "remove", "origin"], here)
    remote_url = f"https://{token}@github.com/{full_name}.git"
    if not run_git(["remote", "add", "origin", remote_url], here):
        print("错误：添加 remote 失败。")
        sys.exit(1)

    ok = run_git(["push", "-u", "origin", BRANCH, "--force"], here)
    if ok:
        print(f"🎉 推送成功！仓库地址：https://github.com/{full_name}")
    else:
        print("❌ 推送失败，请检查：网络连通性、Token 是否具备 repo 权限、仓库是否已存在。")


if __name__ == "__main__":
    main()
