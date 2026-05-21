# -*- coding: utf-8 -*-
"""
PyInstaller 打包脚本
用法: python build.py

依赖:
  pip install pyinstaller flask selenium requests webdriver-manager

输出: dist/wechat-tool/ 目录，打包为 ZIP 即可分发
"""

import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
SPEC_FILE = os.path.join(BASE_DIR, "wechat-tool.spec")


def clean():
    """清理旧的构建产物"""
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
    if os.path.exists(SPEC_FILE):
        os.remove(SPEC_FILE)
    print("[OK] 清理完成")


def build():
    """执行 PyInstaller 打包"""
    print("[INFO] 开始打包...")

    # 确保依赖已安装
    try:
        import flask  # noqa
        import selenium  # noqa
        import requests  # noqa
    except ImportError as e:
        print(f"[ERR] 缺少依赖: {e}")
        print("请先执行: pip install flask selenium requests webdriver-manager pyinstaller")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--name=wechat-tool",
        "--add-data", f"static{os.pathsep}static",
        "--noconfirm",
        "--log-level=INFO",
        os.path.join(BASE_DIR, "app.py"),
    ]

    subprocess.check_call(cmd, cwd=BASE_DIR)
    print(f"[OK] 打包完成！输出目录: {DIST_DIR}")
    return os.path.join(DIST_DIR, "wechat-tool")


def make_zip(dist_path):
    """将打包结果打包为 ZIP"""
    zip_name = os.path.join(BASE_DIR, "wechat-tool.zip")
    if os.path.exists(zip_name):
        os.remove(zip_name)
    shutil.make_archive(
        os.path.join(BASE_DIR, "wechat-tool"),
        "zip",
        DIST_DIR,
        "wechat-tool",
    )
    print(f"[OK] ZIP 包已创建: {zip_name}")
    return zip_name


def print_instructions(zip_path):
    """打印使用说明"""
    size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"\n{'='*60}")
    print(f"  打包完成！ZIP 大小: {size:.1f} MB")
    print(f"  ZIP 文件: {zip_path}")
    print(f"{'='*60}")
    print(f"\n使用方法:")
    print(f"  1. 将 {os.path.basename(zip_path)} 分发给用户")
    print(f"  2. 用户解压到任意目录")
    print(f"  3. 双击 wechat-tool.exe")
    print(f"  4. 浏览器自动打开 http://localhost:5000")
    print(f"\n注意:")
    print(f"  - 首次使用需要登录微信（扫码）")
    print(f"  - 确保系统已安装 Microsoft Edge 浏览器")
    print(f"  - webdriver-manager 会自动下载匹配的 Edge Driver")


if __name__ == "__main__":
    clean()
    dist_path = build()
    zip_path = make_zip(dist_path)
    print_instructions(zip_path)
