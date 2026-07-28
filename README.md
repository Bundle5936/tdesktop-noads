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
| **本地大会员** | 默认开；仅覆盖部分使用 `Session::premium()` / `AmPremiumValue()` 的本地 UI 判断，**不能**解锁服务器权益，也不会覆盖所有直接读取用户 Premium 标志的界面 |

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

未开启时使用官方转写。自定义 STT 请求失败后会尝试回退官方转写；非会员账号是否能使用该回退仍取决于官方服务端资格。

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

## CI 说明（重要）

本仓库是**私有仓库**。GitHub Actions 私有额度通常每月约 **2000 分钟**，Windows 按 **2 倍**计费。

一次完整 Windows 编译经常要：

- 准备依赖库：3~5 小时 → 约 360~600 计费分钟
- 编译主程序：再 3~6 小时 → 约 360~720 计费分钟

历史排查结论：

1. 2026-07-21 到 07-25，多次 Windows 长构建累计约 **3000+ 计费分钟**
2. 额度耗尽后，从 07-26 起所有 workflow 都变成：
   - 运行 2~3 秒
   - `steps: []`
   - `runner_id: 0`
   - 日志 zip 为空
3. 同一账号的**公开仓库** Actions 仍然正常，所以不是 GitHub 全站故障，也不是补丁/workflow YAML 语法问题

当前策略：

| 流程 | 是否自动跑 |
|------|------------|
| `auto-follow` 跟随上游 + 验证补丁 + 创建源码 Release | 是（Ubuntu，便宜） |
| `check` 补丁冒烟 | 是（Ubuntu，便宜） |
| `build-windows` 编译便携包 | **否**，只允许手动 `workflow_dispatch` |

手动编译前请先打开：

`GitHub -> Settings -> Billing and plans -> Actions`

确认私有仓库还有剩余分钟，再运行 `build-windows`，并把 `confirm_billing` 勾成 true。

可选处理：

1. 等下个月额度重置
2. 购买 Actions 分钟包
3. 把仓库改成 public
4. 使用自托管 Windows Runner

## Secrets（建议）

| Name | 说明 |
|------|------|
| `TDESKTOP_API_ID` / `TDESKTOP_API_HASH` | https://my.telegram.org/apps |

不配则用公开测试 API `611335`。

## 风险

- 非官方客户端  
- API Key 费用与隐私自负  
- localPremium ≠ 真 Premium，且只是部分本地 UI 伪装
- API Key 保存在 Telegram Desktop 的本地 experimental-options JSON 中；PasswordInput 只负责界面遮罩，并非系统密钥库加密
- 未签名可能触发 SmartScreen  

## License

上游遵循 Telegram Desktop 许可。本仓库脚本可按 MIT 使用。
