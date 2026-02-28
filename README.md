
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_whatslinkInfo?name=astrbot_plugin_whatslinkInfo&theme=rule34&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_whatslinkInfo

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 磁链解析插件 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-ttlvip-blue)](https://github.com/ttlvip)

</div>


一个[Astrbot](https://github.com/AstrBotDevs/AstrBot)插件，它能自动识别聊天中的磁力链接，并调用 [whatslink.info](https://whatslink.info/) 提供的 API 来生成包含资源详情和截图的预览消息。

## ✨ 功能特性

- **自动识别**: 无需任何指令，在聊天中发送磁力链接即可自动触发。
- **信息丰富**: 显示资源的名称、总大小、文件数量和内容类型。
- **截图预览**: 可配置是否显示由 API 提供的资源截图。
- **智能发送**:
  - 在 QQ/OneBot 平台下，可配置使用**合并转发**的形式发送，避免长消息刷屏。
  - 自动引用原始消息进行回复，交互清晰。
  - 发送“解析中”的提示后**自动撤回**，保持聊天界面整洁。

## 个人修改版新增特性

本仓库代码经过个人深度定制和优化，主要增加了以下核心功能以提升体验和降低封号风险：

1. **触发词防误触**：
   - 解析前置条件增强。现在必须在消息文本中包含关键词 **`验车`** 并且附带磁力链接才会触发解析，避免日常聊天中的普通链接被误解析。
2. **合并转发身份优化**：
   - 修复了合并转发消息的发送人（卡片顶部）显示为触发者本人的问题，现在统一由虚拟账号身份 **`资源解析`** 发送，避免群内引起误会。
3. **截图“防风控”动态混淆（核心）**：
   - 截取封面图片时不再直接请求并在底层发送原图链接，而是预先下载到内存中。
   - 动态微调图片的 4 个边角像素 RGB（肉眼完全不可见），并重设随机导出质量。
   - 本地临时生成具备**全新 MD5** 的防风控图片并发送，发送完毕后**自动销毁**。这极大程度地规避了常见协议端发送老旧截图导致的账号被冻结（1200 / -11 错误）。
4. **稳定降级策略 (Fallback)**：
   - 即使遭遇极其严格的群聊合并转发封锁限制，在捕获转发失败异常后，Bot 也会立刻剥离所有截图，并降级为**带警告提示的普通图文消息**重新发给用户，确保资源绝不漏发。

## 💿 安装

在 AstrBot  插件市场搜索 `astrbot_plugin_whatslinkinfo` 并安装。

## 📖 使用方法

在任意聊天中发送包含磁力链接的消息即可。插件会自动处理并回复预览信息。

## ⚙️ 配置项

你可以在 AstrBot  的插件配置页面找到本插件的设置项。

| 配置项           | 类型      | 默认值                               | 描述                                                               |
| ---------------- | --------- | ------------------------------------ | ------------------------------------------------------------------ |
| `timeout`        | `number`  | `10000`                              | 请求 API 的超时时间（毫秒）。                                      |
| `useForward`     | `boolean` | `false`                              | 在 QQ/OneBot 平台使用合并转发的形式发送结果。                      |
| `showScreenshot` | `boolean` | `true`                               | 是否在结果中显示资源截图。                                         |



## 📜 免责声明

本插件仅作为技术学习和研究目的，所有数据均来源于第三方 API ([whatslink.info](https://whatslink.info/))。

插件作者不存储、不分发、不制作任何资源文件，也不对通过磁力链接获取的内容的合法性、安全性、准确性负责。

请用户在使用本插件时，严格遵守当地法律法规。任何因使用本插件而产生的法律后果，由用户自行承担。

## 📝 许可

[MIT License](https://github.com/ttlvip/astrbot_plugin_whatslinkInfo/blob/master/LICENSE) © 2025 ttlvip
