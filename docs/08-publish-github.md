# 上传到 GitHub（以及后续维护）

本仓库当前发布在 **https://github.com/Ethan-upgrade/dify-market-research-assistant**（public）。
下面是「从零把它推上去」的三种方式，以及几个后续维护动作。

## 一、方式 A：GitHub CLI（最快，本仓库就是这么做出来的）

```powershell
cd D:\dsh-workplace\dify-market-research-assistant
git init -b main
git add -A
git commit -m "feat: 市场调研报告助手"

# 建仓库 + 设 origin + 推送，一条命令搞定
gh repo create dify-market-research-assistant --public --source=. --remote=origin --push `
   --description "市场调研报告助手：Dify Chatflow + 零依赖 Python 实现"
```

要求：`gh auth status` 已登录，token 至少含 `repo` scope。

## 二、方式 B：先在网页建空仓库，再推

1. https://github.com/new → 填名字 → **不要**勾「Add a README」→ Create。
2. 本地：

```powershell
git init -b main
git add -A
git commit -m "feat: 市场调研报告助手"
git remote add origin https://github.com/<你的用户名>/dify-market-research-assistant.git
git push -u origin main
```

## 三、方式 C：只要一份自己的副本

网页右上 **Fork**，或 `git clone` 后删掉 `.git` 重新 `git init` 当自己项目用。

## 四、私有仓库 / 改名

```powershell
gh repo edit --visibility private          # 转私有
gh repo edit --accept-visibility-change-consequences
gh repo rename new-name                    # 改名
```

## 五、CI 怎么启用（重要）

`.github/workflows/ci.yml` 能跑单测 + DSL 校验，但**推 workflow 文件需要 token 有 `workflow` scope**。
本仓库当前的 gh token 只有 `gist / read:org / repo`，所以 CI 配置暂存在 [`ci/github-actions-ci.yml`](../ci/github-actions-ci.yml)。

启用方式二选一：

```powershell
# 1) 补授权后本地推送
gh auth refresh -s workflow
New-Item -ItemType Directory -Force .github\workflows
Copy-Item ci\github-actions-ci.yml .github\workflows\ci.yml
git add .github && git commit -m "ci: enable GitHub Actions" && git push
```

2）直接在网页上新建 `.github/workflows/ci.yml`，把 `ci/github-actions-ci.yml` 的内容粘进去（网页操作不受 scope 限制）。

> 报错原文会是这样：`refusing to allow an OAuth App to create or update workflow .github/workflows/ci.yml without workflow scope`——不是你写错了，是授权范围问题。

## 六、日常维护

```powershell
# 改完跑一遍
cd standalone; python tests/test_nodes.py; python tests/test_search.py

# 打版本
git tag -a v3.0.0 -m "v3.0.0: standalone + DSL v3"
git push origin v3.0.0
gh release create v3.0.0 --generate-notes

# 发布后用发布版 API 回归（需要 Dify 在跑）
python scripts/verify_published.py --mode full --out report.md
```

## 七、提交前必须检查的三件事

1. **别把 Key 提交上去**：`.env`、`*.key`、`secrets.json` 已在 `.gitignore` 里；
   `git status` 里出现它们要先确认。
2. **DSL 里的环境变量值必须是空的**（`value: ""`），Key 只在 Dify 应用内填。
3. **脚本里不许写死账号密码**：本仓库所有脚本只读环境变量。

扫一遍：

```powershell
git grep -nE "tvly-[A-Za-z0-9]{12,}|sk-[A-Za-z0-9]{20,}" -- . ':!docs'
```
