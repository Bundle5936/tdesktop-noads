# tdesktop-noads

**纯 GitHub**：自动跟随官方 Telegram Desktop，打补丁，编译 **Windows x64 便携包**。

## 功能（中文设置开关）

在客户端：

**设置 → 高级 → 实验性功能（Experimental）**

会出现两个 **中文** 开关（默认都开）：

| 开关 | 说明 |
|------|------|
| **禁用赞助广告** | 关闭频道/机器人赞助消息（仅本客户端） |
| **本地大会员** | UI 伪装 Premium；**不能**解锁服务器校验权益；改后建议重启 |

底层补丁：

| 文件 | 作用 |
|------|------|
| `0001-no-sponsored-messages.patch` | 去广告 + 注册开关 |
| `0002-local-premium.patch` | 本地大会员 + 注册开关 |
| `0003-settings-zh-toggles.patch` | 把开关挂到「实验性功能」页 |

### localPremium 能 / 不能

| 通常有效（客户端） | 通常无效（服务器） |
|--------------------|--------------------|
| 界面显示会员 | 更大上传体积 |
| 部分本地限制/入口 | 真会员专属业务 |

## 怎么用便携包

Release 里的 `tportable-x64-noads-<version>.zip`：

1. 解压任意目录  
2. 运行 `Telegram.exe`  
3. 数据在旁边 `tdata/`  
4. 语言：设置里可切 **简体中文**（官方语言包）  
5. 功能开关：设置 → 高级 → **实验性功能**

## 自动流程

```text
auto-follow（每 6h）
  → 官方新版本 + 补丁验证 / auto-heal
  → 触发 build-windows
       → 官方源码 + 三补丁 → 编译 → portable zip
```

## Secrets（建议）

| Name | 说明 |
|------|------|
| `TDESKTOP_API_ID` | https://my.telegram.org/apps |
| `TDESKTOP_API_HASH` | 同上 |

不配则用官方公开测试 API（`611335`）。

## 和其它魔改的关系

- **AyuGram Desktop**：完整 fork + 大量功能（Ghost、保存等）；我们只借「可开关」思路。  
- **Forkgram**：一堆 QoL（方形头像、置顶窗口、默认双向删除等），见下文对照；**未**全部移植。  
- 本仓库：**补丁化** 去广告 + 本地大会员 + 中文实验开关。

## 风险

- 非官方客户端  
- localPremium ≠ 真 Premium  
- 未签名，SmartScreen 可能拦截  

## License

上游遵循 Telegram Desktop 许可。本仓库脚本可按 MIT 使用。
