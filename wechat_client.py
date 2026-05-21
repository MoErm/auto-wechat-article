# -*- coding: utf-8 -*-
"""
微信公众平台登录 + CDN 图片上传
"""

import os
import re
import time
import json
import logging

import requests
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
)


class WeChatClient:
    """微信公众平台客户端 — 登录 + CDN 上传"""

    def __init__(self):
        self.driver = None
        self.token = None
        self.uin = None
        self.session = requests.Session()
        self.logged_in = False

    @property
    def is_logged_in(self):
        return self.logged_in and self.token is not None

    def login(self, timeout=120):
        """打开 Edge 浏览器 → 用户扫码 → 提取 token + cookies"""
        options = Options()
        options.add_argument("--window-size=1280,800")
        options.add_argument(f"user-agent={USER_AGENT}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Edge(options=options)
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """
        })

        logger.info("正在打开微信公众号后台...")
        self.driver.get("https://mp.weixin.qq.com/")

        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: "token=" in d.current_url
            )
        except Exception:
            logger.error("登录超时或失败")
            self.close()
            return False

        time.sleep(1.5)
        url = self.driver.current_url

        token_match = re.search(r"token=([\w-]+)", url)
        uin_match = re.search(r"uin=([\w-]+)", url)

        if not token_match:
            logger.error("无法从 URL 提取 token")
            self.close()
            return False

        self.token = token_match.group(1)
        self.uin = uin_match.group(1) if uin_match else ""
        logger.info(f"登录成功！token: {self.token}, uin: {self.uin}")

        for c in self.driver.get_cookies():
            self.session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

        self.logged_in = True
        logger.info("登录完成，浏览器保持打开")
        return True

    def upload_image(self, file_path):
        """上传图片到微信 CDN，返回 CDN URL"""
        if not self.is_logged_in:
            logger.error("未登录，无法上传")
            return None
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None

        abs_path = os.path.abspath(file_path)
        filename = os.path.basename(file_path)

        # 1. 通过 API 上传获取素材 ID
        content_id = self._upload_material(abs_path, filename)
        if not content_id:
            return None

        logger.info(f"素材上传成功，content_id: {content_id}")

        # 2. 构造 CDN URL 并验证
        cdn_url = self._build_cdn_url(content_id, filename)
        if cdn_url:
            logger.info(f"CDN URL: {cdn_url}")
            return cdn_url

        # 3. 构造失败时尝试通过编辑器上传
        logger.warning("CDN URL 构造失败，尝试通过编辑器上传...")
        cdn_url = self._upload_via_editor(abs_path, filename)
        return cdn_url

    def _upload_material(self, abs_path, filename):
        """调用微信文件上传 API，返回素材 content ID"""
        upload_url = (
            f"https://mp.weixin.qq.com/cgi-bin/filetransfer"
            f"?action=upload_material&f=json&writetype=doublewrite"
            f"&beginsub=1&token={self.token}&lang=zh_CN"
        )
        mime_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "gif": "image/gif", "webp": "image/webp",
        }
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "jpg"
        mime = mime_map.get(ext, "image/jpeg")
        timestamp = str(int(time.time() * 1000))

        with open(abs_path, "rb") as f:
            files = {
                "file": (filename, f, mime),
                "t": (None, "portal-article"),
                "id": (None, timestamp),
            }
            resp = self.session.post(upload_url, files=files, headers={
                "User-Agent": USER_AGENT,
                "Referer": (
                    f"https://mp.weixin.qq.com/cgi-bin/appmsg"
                    f"?t=media/appmsg_edit_v2&action=edit"
                    f"&token={self.token}&lang=zh_CN"
                ),
                "X-Requested-With": "XMLHttpRequest",
            })

        try:
            data = resp.json()
        except Exception:
            logger.error(f"API 响应解析失败: {resp.text[:500]}")
            return None

        logger.info(f"API 上传响应: {json.dumps(data, ensure_ascii=False)}")

        if data.get("base_resp", {}).get("ret") != 0:
            logger.error(f"API 上传失败: {data}")
            return None

        return data.get("content")

    def _build_cdn_url(self, content_id, filename):
        """根据素材 content_id 和账号信息构造 CDN URL 并验证"""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "jpg"
        wx_fmt = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}.get(ext, "jpeg")

        candidates = []
        uin = self.uin or ""

        # 多种可能的 URL 格式
        if uin:
            candidates.append(
                f"https://mmbiz.qpic.cn/sz_mmbiz_{ext}/"
                f"{uin}/{content_id}/0?wx_fmt={wx_fmt}"
            )
            candidates.append(
                f"https://mmbiz.qpic.cn/mmbiz_{ext}/"
                f"{uin}/{content_id}/0?wx_fmt={wx_fmt}"
            )
            candidates.append(
                f"https://mmbiz.qpic.cn/sz_mmbiz_{ext}/"
                f"{uin}_{content_id}/{content_id}/0?wx_fmt={wx_fmt}"
            )
            candidates.append(
                f"https://mmbiz.qpic.cn/mmbiz_{ext}/"
                f"{uin}_{content_id}/{content_id}/0?wx_fmt={wx_fmt}"
            )

        # 无 uin 时也尝试通用格式
        candidates.append(
            f"https://mmbiz.qpic.cn/mmbiz_{ext}/"
            f"{content_id}/0?wx_fmt={wx_fmt}"
        )

        # 逐条验证
        for url in candidates:
            try:
                r = requests.head(url, timeout=5, headers={"User-Agent": USER_AGENT})
                if r.status_code < 400:
                    logger.info(f"CDN URL 验证成功: {url}")
                    return url
                logger.info(f"CDN URL 不可达 ({r.status_code}): {url}")
            except Exception as e:
                logger.info(f"CDN URL 验证异常: {url} -> {e}")

        # 验证失败也返回第一个候选（有可能 HEAD 请求被拒绝但实际可用）
        if candidates:
            logger.warning(f"所有候选 URL 验证失败，返回第一个: {candidates[0]}")
            return candidates[0]

        return None

    def _upload_via_editor(self, abs_path, filename):
        """通过编辑器上传图片并提取 CDN URL"""
        try:
            driver = self.driver

            # 打开编辑器
            editor_url = (
                f"https://mp.weixin.qq.com/cgi-bin/appmsg"
                f"?t=media/appmsg_edit_v2&action=edit"
                f"&token={self.token}&lang=zh_CN"
            )
            driver.get(editor_url)
            time.sleep(3)

            # 查找文件上传 input 并发送文件路径
            uploaded = False
            for sel in [
                "input[type=file]",
                'input[accept*="image"]',
                'input[name="file"]',
            ]:
                try:
                    inputs = driver.find_elements("css selector", sel)
                    for inp in inputs:
                        try:
                            inp.send_keys(abs_path)
                            uploaded = True
                            logger.info(f"通过 {sel} 上传文件")
                            time.sleep(5)
                            break
                        except Exception:
                            continue
                    if uploaded:
                        break
                except Exception:
                    continue

            if not uploaded:
                logger.warning("未找到文件上传 input")
                return None

            # 提取新出现的 CDN URL
            time.sleep(2)
            cdn_urls = driver.execute_script("""
                const imgs = document.querySelectorAll('img');
                const urls = [];
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src.indexOf('mmbiz.qpic.cn') !== -1) {
                        urls.push(src);
                    }
                }
                return urls;
            """)

            if cdn_urls and len(cdn_urls) > 0:
                # 取最后一个（最新插入的）
                result = cdn_urls[-1]
                logger.info(f"编辑器上传提取 CDN URL: {result}")
                return result

            logger.warning("编辑器中未找到 CDN URL")
        except Exception as e:
            logger.warning(f"编辑器上传失败: {e}")

        return None

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
