# tdesktop-noads

**纯 GitHub**：自动跟随官方 [Telegram Desktop](https://github.com/telegramdesktop/tdesktop)，打上去广告补丁，并编译 **Windows x64 便携包**。

> 推到 GitHub 并配好 Secrets 后，本机可以不管。  
> 下载 Release 里的 `tportable-x64-noads-*.zip` 解压即可用。

## 你最终拿到什么

| 产物 | 说明 |
|------|------|
| `tportable-x64-noads-<version>.zip` | **可运行便携包**（Telegram.exe + portable 标记） |
| `0001-no-sponsored-messages.patch` | 源码补丁（备份） |
| `versions/current.json` | 当前跟随的官方版本 |

**不是**在官方 exe 上二进制打补丁，而是：

```text
官方源码 tag
  → 打 no-ads 源码补丁
  → Windows CI 编译 Release
  → 打成 portable zip 挂到 Release
```

## 自动流水线

```text
每 6 小时 / 手动
  auto-follow
    ├─ 有新官方版本且补丁 OK（或自动 heal）
    │    → 更新 pin + tag + Release 说明
    │    → 触发 build-windows
    │         → 编译 → tportable-x64-noads-*.zip
    └─ 无法 heal → 开 Issue
```

## 一次性配置（只需一次）

### 1. 仓库 Secrets（强烈建议）

GitHub → **Settings → Secrets and variables → Actions** 添加：

| Name | 值 |
|------|-----|
| `TDESKTOP_API_ID` | 你的 [api_id](https://my.telegram.org/apps) |
| `TDESKTOP_API_HASH` | 你的 api_hash |

不配也能编，但会用 Telegram **公开测试 API**（共用、可能限流）。  
**私人使用务必配自己的。**

### 2. 打开 Actions

确保 Actions 已启用。私有仓库注意每月分钟数额度。

### 3. 手动跑第一次编译

**Actions → build-windows → Run workflow**

首次会拉依赖/Qt，可能要 **1～3 小时**。成功后到：

**Releases → 对应 tag → 下载 zip**

解压后运行 `Telegram.exe`（旁有 `portable` 文件，数据在 `tdata/`）。

## 日常

不用操作。官方发新版后，仓库会自动：

1. 更新 pin  
2. 编译新便携包  
3. 挂到 Release  

## 本地（可选，一般不需要）

```bash
python cli/tdesktop_noads.py prepare --tag v7.0.3
# 再按官方 building-win.md 编译
```

## 风险说明

- 非官方客户端，账号风险自负  
- 只是客户端隐藏 Sponsored Messages，**不是** Premium  
- 自编译未签名，Windows SmartScreen 可能警告  

## License

上游代码遵循 Telegram Desktop 许可。本仓库脚本/workflow 可按 MIT 使用。
