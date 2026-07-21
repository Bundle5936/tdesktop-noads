# tdesktop-noads

**纯 GitHub**：自动跟随官方 Telegram Desktop，打补丁，编译 **Windows x64 便携包**。

## 中文设置页（独立一页）

打开客户端后：

```text
设置 → 去广告与本地会员
```

页内两个开关（**默认开启**，中文）：

| 开关 | 说明 |
|------|------|
| **禁用赞助广告** | 关闭频道/机器人赞助消息（仅本客户端） |
| **本地大会员** | UI 伪装 Premium；**不能**解锁服务器校验权益；改后建议重启 |

### 补丁

| 文件 | 作用 |
|------|------|
| `0001-no-sponsored-messages.patch` | 去广告逻辑 + 选项定义 |
| `0002-local-premium.patch` | 本地大会员逻辑 + 选项定义 |
| `0003-settings-noads-page.patch` | **独立设置页** + 主设置入口 + CMake |

### localPremium 能 / 不能

| 通常有效（客户端） | 通常无效（服务器） |
|--------------------|--------------------|
| 界面显示会员 | 更大上传体积 |
| 部分本地限制/入口 | 真会员专属业务 |

## 便携包

Release：`tportable-x64-noads-<version>.zip`

1. 解压任意目录  
2. 运行 `Telegram.exe`（数据在 `tdata/`）  
3. 语言可切官方简体中文  
4. 功能：`设置 → 去广告与本地会员`

## 自动流程

```text
auto-follow（每 6h）
  → 官方新版本 + 补丁验证 / auto-heal
  → build-windows → portable zip
```

## Secrets（建议）

| Name | 说明 |
|------|------|
| `TDESKTOP_API_ID` | https://my.telegram.org/apps |
| `TDESKTOP_API_HASH` | 同上 |

不配则用公开测试 API `611335`。

## 风险

- 非官方客户端  
- localPremium ≠ 真 Premium  
- 未签名，SmartScreen 可能拦截  

## License

上游遵循 Telegram Desktop 许可。本仓库脚本可按 MIT 使用。
