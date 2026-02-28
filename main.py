"""
AstrBot 插件：whatslink.info 磁链解析器
- 自动识别消息中的 magnet: 链接
- 调用 https://whatslink.info/api/v1/link?url=... 获取资源信息
- 支持插件配置：timeout（毫秒），useForward（合并转发，QQ/OneBot），showScreenshot（显示截图）

中文注释已添加。
"""
from __future__ import annotations

import re
import aiohttp
import asyncio
import io
import base64
import random
import os
import uuid
from typing import List
from PIL import Image as PILImage

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain, Image, Node, Nodes


MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+)", re.IGNORECASE)
API_URL = "https://whatslink.info/api/v1/link"


def _human_readable_size(num: int) -> str:
    """将字节数格式化为人类可读的字符串（中文单位）。"""
    if num is None:
        return "未知"
    try:
        num = int(num)
    except Exception:
        return str(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.2f}{unit}"
        num /= 1024
    return f"{num:.2f}PB"


@register("astrbot_plugin_whatslinkInfo", "Zhalslar", "磁链解析插件（whatslink.info）", "1.0.0")
class WhatslinkPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.context = context
        self.config = config or {}

    async def initialize(self):
        """异步初始化（可选）"""

    async def _call_api(self, url: str, timeout_ms: int = 10000) -> dict | None:
        """调用 whatslink.info API 并返回 JSON，失败返回 None。"""
        q = {"url": url}
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000 if timeout_ms else None)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(API_URL, params=q, timeout=timeout) as resp:
                    if resp.status != 200:
                        logger.error(f"whatslink.info 返回状态码: {resp.status}")
                        return None
                    data = await resp.json()
                    return data
        except asyncio.TimeoutError:
            logger.warning("whatslink.info 请求超时")
            return None
        except Exception as e:
            logger.error(f"whatslink.info 请求出错: {e}")
            return None

    async def _obfuscate_image(self, url: str, timeout_ms: int = 10000) -> str | None:
        """下载图片并在内存中进行混淆降低风控概率，并存到本地临时文件返回路径"""
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000 if timeout_ms else None)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status != 200:
                        logger.error(f"下载截图失败，状态码: {resp.status}")
                        return None
                    img_bytes = await resp.read()
                    
            # 加载并处理图片
            with io.BytesIO(img_bytes) as in_buf:
                with PILImage.open(in_buf) as img:
                    img = img.convert("RGB")
                    pixels = img.load()
                    width, height = img.size
                    
                    # 随机修改四个角的像素值（微小改变肉眼不可见，足以改变MD5）
                    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
                    for x, y in corners:
                        r, g, b = pixels[x, y]
                        pixels[x, y] = (
                            max(0, min(255, r + random.randint(-5, 5))),
                            max(0, min(255, g + random.randint(-5, 5))),
                            max(0, min(255, b + random.randint(-5, 5)))
                        )
                    
                    # 保存图片到临时文件
                    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_pics")
                    if not os.path.exists(tmp_dir):
                        os.makedirs(tmp_dir)
                    
                    filename = f"{uuid.uuid4().hex}.jpg"
                    filepath = os.path.join(tmp_dir, filename)
                    
                    img.save(filepath, format="JPEG", quality=random.randint(90, 95))
                    return filepath
                        
        except Exception as e:
            logger.error(f"处理图片混淆出错: {e}")
            return None

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，自动识别并解析磁链（magnet:）。

        行为：
        - 当消息中包含 magnet 链接时，触发解析流程。
        - 先发送一条“解析中...”提示（平台不一定支持撤回，本插件会尽量减少噪音）。
        - 请求 API，格式化并发送解析结果；根据配置可发送合并转发（QQ/OneBot）。
        """
        text = event.get_message_str() or ""
        if not text:
            return

        # 必须包含触发词“我要验牌 ”才去解析，否则原样忽略
        if "我要验牌 " not in text:
            return

        magnets = MAGNET_RE.findall(text)
        if not magnets:
            return

        # 读取配置
        allowed_users = self.config.get("allowed_users", [])
        # 如果配置了允许的用户，且当前发送者不在列表中，则忽略
        sender_id = str(event.get_sender_id())
        if allowed_users and sender_id not in allowed_users:
            return

        timeout = int(self.config.get("timeout", 10000))
        use_forward = bool(self.config.get("useForward", True))
        show_screenshot = bool(self.config.get("showScreenshot", True))

        # 先发“解析中”的提示（尽量简短）
        try:
            yield event.plain_result("解析磁链中...")
        except Exception:
            # 发送失败不影响主流程
            pass

        results_to_send: List[MessageEventResult] = []

        for m in magnets:
            api_ret = await self._call_api(m, timeout_ms=timeout)
            if not api_ret:
                # 请求失败
                r = MessageEventResult().message(f"解析失败: {m}")
                results_to_send.append(r)
                continue

            # 解析响应字段，按 API 文档处理
            err = api_ret.get("error") or ""
            if err:
                results_to_send.append(MessageEventResult().message(f"解析失败: {err}"))
                continue

            name = api_ret.get("name", "未知名称")
            size = api_ret.get("size")
            count = api_ret.get("count")
            file_type = api_ret.get("file_type", api_ret.get("type", ""))
            screenshots = api_ret.get("screenshots", []) or []

            # 构建要显示的文本：要求不展示类型和来源，仅显示名称、文件数量与总大小
            header = f"名称: {name}\n文件数量: {count}\n总大小: {size} ({_human_readable_size(size)})\n"

            # 如果需要显示截图，准备所有截图的本地临时文件路径（防风控混淆处理）
            shots: List[str] = []
            if show_screenshot and isinstance(screenshots, list) and len(screenshots) > 0:
                for s in screenshots:
                    url = s.get("screenshot")
                    if url:
                        tmp_path = await self._obfuscate_image(url, timeout_ms=timeout)
                        if tmp_path:
                            shots.append(tmp_path)

            # 构造 MessageEventResult
            if use_forward and event.get_platform_name() in ("aiocqhttp", "qq", "qq_official", "onebot"):
                # 对于 QQ/OneBot 平台，使用合并转发（Nodes）以避免刷屏。
                # Node 内容是一个消息链（列表），此处仅放入文本和可能的图片
                content = [Plain(header)]
                # 将所有截图附加为图片段
                for path in shots:
                    content.append(Image.fromFileSystem(path))
                # 修改发送人为虚拟的 Bot，解决“显示发送人是对方（触发者）”的问题
                node = Node(content=content, name="资源解析", uin="10000")
                nodes = Nodes(nodes=[node])
                mer = MessageEventResult()
                mer.chain = [nodes]
                results_to_send.append(mer)
            else:
                # 普通平台或不开启合并转发，直接发送文本 + 图片
                mer = MessageEventResult().message(header)
                for path in shots:
                    mer.chain.append(Image.fromFileSystem(path))
                results_to_send.append(mer)

        # 逐条发送解析结果。使用 context.send_message 主动发送，避免影响当前事件的传播控制。
        for r in results_to_send:
            try:
                await self.context.send_message(event.unified_msg_origin, r)
            except Exception as e:
                logger.error(f"发送解析结果失败: {e}")
                # 如果是合并转发消息发送失败，可能是由于平台风控或限制，这里尝试降级为普通图文消息重新发送
                if getattr(r, 'chain', None) and len(r.chain) > 0 and isinstance(r.chain[0], Nodes):
                    try:
                        logger.warning("合并转发失败，尝试降级为普通消息发送...")
                        fallback_mer = MessageEventResult()
                        fallback_mer.chain.append(Plain("⚠️ 合并转发失败（可能被风控），已为您自动降级显示：\n"))
                        
                        # 把 Nodes 里所有的图文组件提取出来作为普通消息链
                        for _node in r.chain[0].nodes:
                            for _comp in getattr(_node, 'content', []):
                                fallback_mer.chain.append(_comp)
                        
                        await self.context.send_message(event.unified_msg_origin, fallback_mer)
                        logger.info("降级为普通图文消息发送成功！")
                    except Exception as fallback_e:
                        logger.error(f"降级发送普通消息也失败了: {fallback_e}")
        
        # 发送完毕后，清理刚才生成的临时图片文件，防止硬盘被占满
        for path in shots:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"无法删除临时文件 {path}: {e}")

    async def terminate(self):
        """插件被卸载/停用时调用（可选）"""
        return
