# tdesktop-noads

**纯 GitHub**：自动跟随官方 Telegram Desktop，打补丁，编译 **Windows x64 便携包**。

## 设置入口

```text
设置 → 去广告 / AI / 语音
```

### 基础

| 开关 | 说明 |
|------|------|
| **禁用赞助广告** | 默认开；仅本客户端 |
| **本地大会员** | 默认开；UI 伪装，**不能**解锁服务器权益 |

### AI 翻译（OpenAI 兼容，真 LLM）

| 项 | 说明 |
|----|------|
| **启用 AI 翻译** | 开后覆盖官方/URL/系统翻译 |
| **Base URL** | 如 `https://api.openai.com/v1` |
| **API Key** | Bearer Token，仅本机 |
| **模型** | 默认 `gpt-4o-mini` |
| **系统提示词** | 可改翻译风格 |

生效范围：**单条翻译 + 自动翻译**（官方 `CreateTranslateProvider` 钩子）。

协议：`POST {base}/chat/completions`。

### 自定义 STT（语音转写）

| 项 | 说明 |
|----|------|
| **启用自定义语音转写** | 开后优先走自建 API；可解非会员锁 |
| **STT Base URL / Key / 模型** | 可留空，默认复用上方 AI 配置；模型默认 `whisper-1` |

协议：`POST {base}/audio/transcriptions`（multipart：`model` + `file`）。

未开启或失败配置时回退官方转写。

## 补丁列表

| 文件 | 作用 |
|------|------|
| `0001` | 去广告 |
| `0002` | 本地大会员 |
| `0003` | 中文设置页 |
| `0004` | LLM 翻译 provider + 工厂接入 |
| `0005` | 自定义 STT + 转写按钮解锁 |

上游改动尽量集中：

- 翻译：只改 `CreateTranslateProvider` 决策 + 新文件  
- STT：只改 `Transcribes::load` / 转写按钮锁 + 新文件  

重新生成 AI 补丁：

```bash
python scripts/gen_ai_patches.py
```

## 便携包

Release：`tportable-x64-noads-<version>.zip`

1. 解压 → `Telegram.exe`  
2. 数据在 `tdata/`  
3. 配置：`设置 → 去广告 / AI / 语音`

## Secrets（建议）

| Name | 说明 |
|------|------|
| `TDESKTOP_API_ID` / `TDESKTOP_API_HASH` | https://my.telegram.org/apps |

不配则用公开测试 API `611335`。

## 风险

- 非官方客户端  
- API Key 费用与隐私自负  
- localPremium ≠ 真 Premium  
- 未签名可能触发 SmartScreen  

## License

上游遵循 Telegram Desktop 许可。本仓库脚本可按 MIT 使用。
