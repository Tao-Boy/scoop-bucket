# Pebrel Scoop bucket

Pebrel 的 Scoop 安装源，支持 Windows x64 和 ARM64。
安装清单参考 [Kuddev/scoop-bucket](https://github.com/Kuddev/scoop-bucket)。

## 安装与更新

先安装 [Scoop](https://scoop.sh/)，再在普通 PowerShell 窗口中执行：

```powershell
scoop bucket add tao-boy https://github.com/Tao-Boy/scoop-bucket
scoop install tao-boy/pebrel
```

安装后可从开始菜单启动 Pebrel，或在终端运行 `pebrel`。

```powershell
scoop update
scoop update pebrel
```

## 每日自动更新

[Update Scoop manifests](https://github.com/Tao-Boy/scoop-bucket/actions/workflows/update.yml)
每天 **01:23 UTC（北京时间 09:23）** 检查
[Kuddev/pebrel 的最新正式 Release](https://github.com/Kuddev/pebrel/releases/latest)，
也可在 Actions 页面点击 **Run workflow** 手动执行。修改工作流、更新脚本或清单时也会检查。

- 只使用上游已发布的 Windows x64、ARM64 ZIP 包；不编译、不运行软件、不创建 Release。
- 两种架构的包均已上传后，更新 `bucket/pebrel.json` 的版本号、下载地址与 SHA256。
- 优先使用 GitHub 为上传资产计算的 SHA256；资产没有该字段时，仅下载 ZIP 计算 SHA256，不解压、不执行。
- 保留安装命令、快捷方式和其他清单字段；忽略预发布版本，禁止降级。
- API 请求失败、包缺失或下载不完整时，任务失败并保留现有 JSON，下次运行重新检查。
- 无变化时不提交；有变化时使用 `github-actions[bot]` 直接提交到 `main`，仅暂存该 JSON 文件。
- 使用内置 `GITHUB_TOKEN` 和 `contents: write` 权限，无需配置个人访问令牌或额外 Secret。

GitHub 定时任务可能延迟。公开仓库连续 60 天没有活动时，GitHub 可能停用定时工作流；
届时需在 Actions 页面重新启用。详见
[GitHub 定时工作流说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。
若仓库启用了禁止直接推送的分支保护规则，需允许该自动化提交，或改用 PR 更新方式。

## 本地检查

需要 Python 3.12 或更高版本，无第三方 Python 依赖：

```sh
python -m unittest discover -s tests -v
python scripts/update_pebrel.py --dry-run
python scripts/update_pebrel.py
```

最后一条命令只修改本地 JSON，不会自动执行 Git 提交。

## 软件来源与卸载

应用包直接来自 [Kuddev/pebrel](https://github.com/Kuddev/pebrel) 的 GitHub Releases。
Scoop 按清单中的 SHA256 校验下载包，并保留完整便携包、辅助文件和许可证。
应用许可证为 GPL-3.0-or-later；附带组件保留各自声明。

```powershell
scoop uninstall pebrel
scoop bucket rm tao-boy
```

卸载清单不会删除安装目录之外的应用设置。
清单安装问题可在本仓库反馈；软件自身问题请反馈至
[Kuddev/pebrel](https://github.com/Kuddev/pebrel/issues)。
