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
from PIL import Image as PILImage, ImageDraw, ImageEnhance

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
        """下载图片并在内存中进行深度混淆（缩放、画盲水印线、加噪）降低风控概率"""
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
                    img = img.convert("RGBA")
                    width, height = img.size
                    
                    # 1. 随机微调尺寸（缩放 98% ~ 102%）
                    scale = random.uniform(0.98, 1.02)
                    new_w, new_h = int(width * scale), int(height * scale)
                    img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
                    
                    # 2. 绘制肉眼不可见的随机干扰线（盲水印抗风控）
                    draw = ImageDraw.Draw(img)
                    for _ in range(random.randint(5, 10)):
                        x1 = random.randint(0, new_w)
                        y1 = random.randint(0, new_h)
                        x2 = random.randint(0, new_w)
                        y2 = random.randint(0, new_h)
                        # 随机极低透明度的颜色 (肉眼完全看不见，但破坏原图矩阵)
                        r_color = (random.randint(0,255), random.randint(0,255), random.randint(0,255), random.randint(1, 3))
                        draw.line((x1, y1, x2, y2), fill=r_color, width=random.randint(1, 3))
                    
                    # 3. 随机噪点覆盖几个点
                    pixels = img.load()
                    for _ in range(random.randint(20, 50)):
                        x = random.randint(0, new_w - 1)
                        y = random.randint(0, new_h - 1)
                        if len(pixels[x, y]) == 4:
                            r, g, b, a = pixels[x, y]
                            pixels[x, y] = (
                                max(0, min(255, r + random.randint(-15, 15))),
                                max(0, min(255, g + random.randint(-15, 15))),
                                max(0, min(255, b + random.randint(-15, 15))),
                                a
                            )
                    
                    # 转换回 RGB 以便保存 JPG
                    img = img.convert("RGB")
                    
                    # 保存图片到临时文件，带有随机亮度微调和随机压缩率
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(random.uniform(0.95, 1.05))
                    
                    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_pics")
                    if not os.path.exists(tmp_dir):
                        os.makedirs(tmp_dir)
                    
                    filename = f"obs_{uuid.uuid4().hex}.jpg"
                    filepath = os.path.join(tmp_dir, filename)
                    
                    img.save(filepath, format="JPEG", quality=random.randint(85, 95))
                    return filepath
                        
        except Exception as e:
            logger.error(f"处理图片深度混淆出错: {e}")
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
            files_list = api_ret.get("files", []) or []

            # 构建要显示的文本
            header = f"【名称】: {name}\n【数量】: {count} 个\n【大小】: {size} ({_human_readable_size(size)})\n"
            
            # 美化展示：列出内部包含的具体文件清单（最多显示前 10 个）
            if files_list:
                header += "\n📄 包含文件列表:\n"
                show_limit = 10
                for idx, f in enumerate(files_list[:show_limit], 1):
                    f_name = f.get("name", "未知")
                    f_size = f.get("size", 0)
                    header += f"  {idx}. {f_name} ({_human_readable_size(f_size)})\n"
                
                if len(files_list) > show_limit:
                    header += f"  ... 以及其他 {len(files_list) - show_limit} 个文件。\n"

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
                                # 极限降级：如果连普通图文都发不出（Timeout / 1200），说明风控极其严格（甚至屏蔽了混淆图）
                                # 此时在降级消息中剔除所有图片，只保留纯文本，以确保资源必须送达
                                if isinstance(_comp, Plain):
                                    fallback_mer.chain.append(_comp)
                        
                        await self.context.send_message(event.unified_msg_origin, fallback_mer)
                        logger.info("极简降级（仅文本）发送成功！")
                    except Exception as fallback_e:
                        logger.error(f"极简降级发送也失败了: {fallback_e}")
        
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
