# -*- coding: utf-8 -*-
"""
微信图文生成桌面工具 - Flask 后端服务
启动方式: python app.py
浏览器打开 http://localhost:5000
"""

import os
import sys
import json
import uuid
import shutil
import logging
import threading
import webbrowser
from datetime import datetime
from html import escape

from flask import Flask, request, jsonify, send_from_directory, send_file

from wechat_client import WeChatClient

# ==================== 配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DATA_FILE = os.path.join(BASE_DIR, "data.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PORT = 5000

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==================== 日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, "app.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ==================== Flask 应用 ====================
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")

# ==================== 数据管理 ====================
data_lock = threading.Lock()


def load_data():
    """从 data.json 加载文件列表和元数据"""
    with data_lock:
        if not os.path.exists(DATA_FILE):
            default = {"files": [], "version": 1}
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
            return default
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"files": [], "version": 1}


def save_data(data):
    """保存数据到 data.json"""
    with data_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def get_file_record(file_id):
    """按 ID 查找文件记录"""
    data = load_data()
    for f in data.get("files", []):
        if f["id"] == file_id:
            return f
    return None


def update_file_record(file_id, updates):
    """更新文件记录中的字段"""
    data = load_data()
    for f in data.get("files", []):
        if f["id"] == file_id:
            f.update(updates)
            save_data(data)
            return True
    return False


# ==================== 微信客户端管理 ====================
wechat_client = WeChatClient()
wechat_lock = threading.Lock()


# ==================== 模板引擎 ====================
def render_loop_template(template, items, thumb_map):
    """渲染循环模板，items 列表中的每项应用一次模板"""
    parts = []
    for idx, item in enumerate(items):
        html = template
        if item.get("type") == "txt":
            content = escape(item.get("content", ""))
            html = html.replace("{{IMAGE}}", f"<p>{content}</p>")
        else:
            img_url = item.get("cdn_url") or thumb_map.get(item["id"], "")
            img_tag = f'<img src="{escape(img_url, quote=True)}" style="max-width:100%;display:block;margin:8px auto;" />'
            html = html.replace("{{IMAGE}}", img_tag)
        html = html.replace("{{TITLE}}", escape(item.get("title", "")))
        html = html.replace("{{INDEX}}", str(idx + 1))
        parts.append(html)
    return "\n".join(parts)


def render_page_template(template, loop_html, title, date, author):
    """渲染页面模板，将循环结果插入 {{CONTENT}}"""
    html = template
    html = html.replace("{{TITLE}}", escape(title))
    html = html.replace("{{DATE}}", escape(date))
    html = html.replace("{{AUTHOR}}", escape(author))
    html = html.replace("{{CONTENT}}", loop_html)
    return html


def wrap_full_html(body_html, title=""):
    """将文章 body 包装为完整 HTML 文档（用于预览）"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{escape(title)}</title>
<style>
body {{ font-family: -apple-system,"Microsoft YaHei",sans-serif; max-width: 677px; margin: 0 auto; padding: 16px; color: #333; line-height: 1.6; }}
img {{ max-width: 100%; height: auto; display: block; margin: 0 auto; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


# ==================== 路由 ====================


@app.route("/")
def index():
    """提供前端页面"""
    return send_from_directory(STATIC_DIR, "index.html")


# ---- 微信登录 ----

@app.route("/api/login", methods=["POST"])
def api_login():
    """启动微信扫码登录（在新线程中打开 Selenium）"""
    def do_login():
        with wechat_lock:
            try:
                logger.info("正在启动微信登录...")
                success = wechat_client.login(timeout=120)
                if success:
                    logger.info("微信登录成功")
                else:
                    logger.error("微信登录失败")
            except Exception as e:
                logger.error(f"微信登录异常: {e}")

    thread = threading.Thread(target=do_login, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "正在打开微信登录窗口，请扫码..."})


@app.route("/api/status", methods=["GET"])
def api_status():
    """查询微信登录状态"""
    with wechat_lock:
        logged_in = wechat_client.is_logged_in
    return jsonify({
        "logged_in": logged_in,
        "token": wechat_client.token if logged_in else None,
    })


# ---- 文件管理 ----

@app.route("/api/files", methods=["GET"])
def api_list_files():
    """获取已上传文件列表"""
    data = load_data()
    files = data.get("files", [])
    return jsonify({"files": files, "count": len(files)})


@app.route("/api/files", methods=["DELETE"])
def api_clear_files():
    """清空所有文件和上传目录"""
    data = load_data()
    for f in data.get("files", []):
        fpath = os.path.join(UPLOAD_DIR, os.path.basename(f.get("path", "")))
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    save_data({"files": [], "version": 1})
    # 也清理 uploads 目录下残余
    for name in os.listdir(UPLOAD_DIR):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except Exception:
            pass
    return jsonify({"success": True})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """上传文件到本地存储"""
    if "files" not in request.files:
        return jsonify({"success": False, "error": "没有选择文件"}), 400

    uploaded_files = request.files.getlist("files")
    if not uploaded_files or uploaded_files[0].filename == "":
        return jsonify({"success": False, "error": "空文件"}), 400

    data = load_data()
    existing = {f["filename"]: f for f in data.get("files", [])}
    count = 0

    for f in uploaded_files:
        orig_name = f.filename
        # 如果同名文件已存在，跳过
        if orig_name in existing:
            continue

        file_id = str(uuid.uuid4())
        ext = orig_name.rsplit(".", 1)[-1] if "." in orig_name else "jpg"
        saved_name = f"{file_id}.{ext}"
        save_path = os.path.join(UPLOAD_DIR, saved_name)
        f.save(save_path)

        record = {
            "type": "img",
            "id": file_id,
            "filename": orig_name,
            "path": saved_name,
            "title": "",
            "content": "",
            "cdn_url": "",
            "uploaded_at": datetime.now().isoformat(),
        }
        data.setdefault("files", []).append(record)
        count += 1
        existing[orig_name] = record

    save_data(data)
    return jsonify({"success": True, "count": count})


@app.route("/api/thumb/<file_id>", methods=["GET"])
def api_thumbnail(file_id):
    """提供文件缩略图"""
    record = get_file_record(file_id)
    if not record:
        return "", 404
    file_path = os.path.join(UPLOAD_DIR, record.get("path", ""))
    if not os.path.exists(file_path):
        return "", 404
    return send_file(file_path)


@app.route("/api/text", methods=["POST"])
def api_add_text():
    """添加一个文本段落"""
    data = load_data()
    record = {
        "type": "txt",
        "id": str(uuid.uuid4()),
        "title": "",
        "content": "",
        "uploaded_at": datetime.now().isoformat(),
    }
    data.setdefault("files", []).append(record)
    save_data(data)
    return jsonify({"success": True, "record": record})


@app.route("/api/files/<file_id>", methods=["PUT"])
def api_update_file(file_id):
    """更新文件元数据"""
    updates = request.json or {}
    allowed = {"title", "content", "caption", "cdn_url"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return jsonify({"success": False, "error": "没有可更新的字段"}), 400
    ok = update_file_record(file_id, filtered)
    return jsonify({"success": ok})


@app.route("/api/files/<file_id>", methods=["DELETE"])
def api_delete_file(file_id):
    """删除指定文件"""
    data = load_data()
    files = data.get("files", [])
    removed = [f for f in files if f["id"] == file_id]
    data["files"] = [f for f in files if f["id"] != file_id]
    save_data(data)
    for f in removed:
        fpath = os.path.join(UPLOAD_DIR, f.get("path", ""))
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    return jsonify({"success": True})


@app.route("/api/reorder", methods=["POST"])
def api_reorder():
    """重新排序文件"""
    order = (request.json or {}).get("order", [])
    if not order:
        return jsonify({"success": False, "error": "缺少 order"}), 400
    data = load_data()
    files = data.get("files", [])
    file_map = {f["id"]: f for f in files}
    new_order = []
    for fid in order:
        if fid in file_map:
            new_order.append(file_map[fid])
    # 添加不在 order 中的文件到末尾
    for f in files:
        if f["id"] not in order:
            new_order.append(f)
    data["files"] = new_order
    save_data(data)
    return jsonify({"success": True})


# ---- CDN 上传 ----

@app.route("/api/upload-wechat", methods=["POST"])
def api_upload_wechat():
    """上传指定文件到微信 CDN"""
    with wechat_lock:
        if not wechat_client.is_logged_in:
            return jsonify({"success": False, "error": "未登录微信，请先登录"}), 401

    file_id = (request.json or {}).get("file_id", "")
    if not file_id:
        return jsonify({"success": False, "error": "缺少 file_id"}), 400

    record = get_file_record(file_id)
    if not record:
        return jsonify({"success": False, "error": "文件不存在"}), 404

    file_path = os.path.join(UPLOAD_DIR, record.get("path", ""))
    if not os.path.exists(file_path):
        return jsonify({"success": False, "error": "文件数据不存在"}), 404

    try:
        with wechat_lock:
            cdn_url = wechat_client.upload_image(file_path)

        if cdn_url:
            update_file_record(file_id, {"cdn_url": cdn_url})
            return jsonify({"success": True, "cdn_url": cdn_url})
        else:
            return jsonify({"success": False, "error": "上传到微信 CDN 失败，请检查登录状态"}), 500
    except Exception as e:
        logger.exception("上传到微信 CDN 异常")
        return jsonify({"success": False, "error": str(e)}), 500


# ---- 预览 & 导出 ----

@app.route("/api/preview", methods=["POST"])
def api_preview():
    """渲染模板并返回预览 HTML（优先使用微信 CDN URL）"""
    body = request.json or {}
    page_template = body.get("page_template", "{{CONTENT}}")
    loop_template = body.get("loop_template", "{{IMAGE}}")
    items = body.get("items", [])
    title = body.get("title", "")
    date = body.get("date", "")
    author = body.get("author", "")

    # 优先用 CDN URL，其次本地缩略图
    thumb_map = {}
    for item in items:
        if item.get("id"):
            record = get_file_record(item["id"])
            if record and record.get("cdn_url"):
                thumb_map[item["id"]] = record["cdn_url"]
            else:
                thumb_map[item["id"]] = f"/api/thumb/{item['id']}"

    loop_html = render_loop_template(loop_template, items, thumb_map)
    article_body = render_page_template(page_template, loop_html, title, date, author)
    full_html = wrap_full_html(article_body, title)

    return jsonify({"html": full_html})


@app.route("/api/export", methods=["POST"])
def api_export():
    """导出最终 HTML（与预览相同，但专用于复制/下载）"""
    body = request.json or {}
    page_template = body.get("page_template", "{{CONTENT}}")
    loop_template = body.get("loop_template", "{{IMAGE}}")
    items = body.get("items", [])
    title = body.get("title", "")
    date = body.get("date", "")
    author = body.get("author", "")

    # 构建图片 URL 映射：优先用 CDN URL
    thumb_map = {}
    for item in items:
        if item.get("id"):
            record = get_file_record(item["id"])
            if record and record.get("cdn_url"):
                thumb_map[item["id"]] = record["cdn_url"]
            else:
                thumb_map[item["id"]] = f"/api/thumb/{item['id']}"

    loop_html = render_loop_template(loop_template, items, thumb_map)
    article_body = render_page_template(page_template, loop_html, title, date, author)
    # 导出时不包装 <html> 标签，保留纯文章 HTML（适合粘贴到微信编辑器）
    return jsonify({"html": article_body})


# ==================== 启动 ====================

def find_free_port(start_port):
    """查找可用端口"""
    import socket
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port  # 实在找不到就用默认


if __name__ == "__main__":
    active_port = find_free_port(PORT)
    if active_port != PORT:
        logger.warning(f"端口 {PORT} 被占用，使用端口 {active_port}")

    # 自动打开浏览器
    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{active_port}")

    threading.Thread(target=open_browser, daemon=True).start()

    logger.info(f"启动服务: http://localhost:{active_port}")
    app.run(host="127.0.0.1", port=active_port, debug=False)
