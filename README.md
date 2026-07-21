# tdesktop-noads

**纯 GitHub**：自动跟随官方 Telegram Desktop，打补丁，编译 **Windows x64 便携包**。

## 补丁

| 文件 | 作用 | 限制 |
|------|------|------|
| `0001-no-sponsored-messages.patch` | 关闭赞助广告 | 仅本客户端 |
| `0002-local-premium.patch` | **本地大会员**（UI 伪装） | **不能**解锁服务器校验功能 |

### localPremium 能做什么 / 不能做什么

| 通常有效（客户端判断） | 通常无效（服务器校验） |
|------------------------|------------------------|
| 界面显示 Premium | 更大上传体积 |
| 部分本地限制/入口 | 官方 Premium 专属贴纸包等 |
| 与去广告补丁配合 | 真正的会员业务权益 |

去广告靠 `0001`，不靠 localPremium。

## 你拿到什么

Release 里的：

`tportable-x64-noads-<version>.zip`

解压 → 运行 `Telegram.exe`（旁有 `portable`，数据在 `tdata/`）。

## 自动流程

```text
auto-follow（每 6h）
  → 官方新版本 + 补丁验证/自动 heal
  → 更新 pin / tag
  → 触发 build-windows
       → 官方源码 + 两补丁 → 编译 → portable zip 挂 Release
```

## 一次性配置

### Secrets（建议）

| Name | 说明 |
|------|------|
| `TDESKTOP_API_ID` | https://my.telegram.org/apps |
| `TDESKTOP_API_HASH` | 同上 |

不配则用公开测试 API（共用、可能限流）。

### 首次编译

Actions → **build-windows** → Run workflow  

首次约 1～3 小时。完成后在 Releases 下载 zip。

## 风险

- 非官方客户端  
- localPremium ≠ 真 Premium  
- 未签名，SmartScreen 可能拦截  

## License

上游遵循 Telegram Desktop 许可。本仓库脚本可按 MIT 使用。
