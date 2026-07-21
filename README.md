# tdesktop-noads

**纯 GitHub 自动跟随**官方 [Telegram Desktop](https://github.com/telegramdesktop/tdesktop) 发版，只保留去赞助广告补丁。

> 推到 GitHub 之后：**本机可以关机**。  
> 更新 / 验证 / 必要时重生补丁 / 打 tag / 发 Release，全部由 Actions 完成。

## 零本地参与流程

```text
官方 telegramdesktop/tdesktop 发布新版本
              │
              ▼
     GitHub Actions（每 6 小时）
              │
     拉官方源码，试现有 patch
              │
     ┌────────┴────────┐
     │ 能 apply        │ 不能 apply
     ▼                 ▼
  更新 pin          自动 heal
  打 tag            （改 3 个入口 → 重生 patch）
  发 Release              │
                    ┌─────┴─────┐
                    │ 成功      │ 仍失败（极少）
                    ▼           ▼
                 提交 patch   开 Issue
                 + pin/tag
```

你**不需要**在电脑上跑任何命令来跟官方。  
唯一可能要人看的情况：上游把广告相关代码改到函数签名都认不出来（很少）。

## 仓库里有什么

```text
versions/current.json          # 当前已验证的官方 tag（CI 自动改）
patches/*.patch                # 去广告补丁（CI 可能自动重生）
cli/tdesktop_noads.py          # Actions 用的脚本
.github/workflows/auto-follow.yml
```

**不包含** tdesktop 完整源码镜像，也不编 Windows 安装包。  
只跟踪「官方这个版本 + 补丁可用」。

## 一次性上线（只需这一次）

把本仓库推到 GitHub 后就不用再管：

```bash
# 仅首次
git init
git add .
git commit -m "init: pure GitHub auto-follow"
# 创建并推送（示例）
gh repo create tdesktop-noads --public --source=. --remote=origin --push
```

然后打开 **Actions → auto-follow → Run workflow** 跑第一次。  
之后每 6 小时自动跟官方。

## 补丁做了什么

只动：`Telegram/SourceFiles/data/components/sponsored_messages.cpp`

| 函数 | 效果 |
|------|------|
| `canHaveFor(History*)` | 关频道 / Bot 广告 |
| `canHaveFor(HistoryItem*)` | 关视频旁广告 |
| `isTopBarFor(History*)` | 关 Bot 顶栏广告 |

全部短路为 `return false`。

## 可选：本地编译（非必须）

CI **不编**安装包。若你自己要可执行文件：

```bash
python cli/tdesktop_noads.py prepare --tag v7.0.3
# 再按官方文档编译 work/src
```

- Windows 构建说明：https://github.com/telegramdesktop/tdesktop/blob/dev/docs/building-win.md  
- API：https://core.telegram.org/api/obtaining_api_id  

## 声明

客户端侧隐藏 Sponsored Messages ≠ 官方 Premium。  
自编译客户端有账号风险，自行判断。

## License

上游代码遵循 Telegram Desktop 许可。本仓库脚本按 MIT 使用即可。
