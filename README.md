# 微信图文生成桌面工具

Flask 后端服务 + 浏览器前端，用于自动生成微信公众号图文草稿。

## 依赖

```bash
pip install flask selenium requests webdriver-manager
```

| 包 | 版本 | 用途 |
|---|---|---|
| flask | >= 3.0 | Web 服务 |
| selenium | >= 4.15 | 浏览器自动化 |
| requests | >= 2.31 | HTTP 请求 |
| webdriver-manager | >= 4.0 | EdgeDriver 自动管理 |

## 启动

```bash
python app.py
```

浏览器打开 http://localhost:5000

## 打包

```bash
pip install pyinstaller
python build.py
```

输出在 `dist/wechat-tool/`


使用方法:
  1. 将 wechat-tool.zip 下载
  2. 用户解压到任意目录
  3. 双击 wechat-tool.exe
  4. 浏览器自动打开 http://localhost:5000

注意:
  - 首次使用需要登录微信（扫码）
  - 确保系统已安装 Microsoft Edge 浏览器
  - webdriver-manager 会自动下载匹配的 Edge Driver