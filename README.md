<p align="center">
  <h1 align="center">CamStream</h1>
  <p align="center">
    <b>将任意摄像头一键变为 RTSP 流媒体源</b><br>
    专为无人机图传、远程监控、局域网视频分发等场景设计
  </p>
  <p align="center">
    <a href="#快速开始">快速开始</a> •
    <a href="#核心特性">核心特性</a> •
    <a href="#使用场景">使用场景</a> •
    <a href="LICENSE">MIT License</a>
  </p>
</p>

---

<p align="center">
  <img src="pictures/界面示例.png" alt="界面预览" width="800">
</p>


## WinUI 3 原生桌面版

仓库新增 C# / WinUI 3 版本，提供摄像头与麦克风选择、RTSP 推流、UDP/TCP、H.264/H.265/NVENC、预览以及首次运行时准备 FFmpeg/MediaMTX。原 Python/PyQt 版本保留。

- 项目：`CamStream.WinUI.csproj`；入口：`App.xaml`、`MainWindow.xaml`
- 使用 Visual Studio 2022 / Windows App SDK / .NET SDK 8.0.425 构建，目标 x64
- 详细说明：[`README-WinUI.md`](README-WinUI.md)

**验证状态：** VS 2022 MSBuild 的 x64 Release 构建通过。当前开发机启动 GUI 时仍在 `USER32.dll` 异常退出（`0xC0000409`），原因待查；真实摄像头与局域网拉流尚未验证。

## 核心特性

- **一键推流** — 选择摄像头，点击「开始推流」，即可生成标准 RTSP 流地址
- **UDP / TCP 双模** — 默认 UDP 低延迟（适合实时图传），可切换 TCP 保证可靠传输
- **GPU 硬件加速** — 支持 NVIDIA NVENC 硬编码，CPU 占用低、延迟小
- **多编码格式** — H.264 / H.265，按需选择画质与带宽平衡
- **自带 RTSP 服务器** — 内置 MediaMTX，开箱即用，无需额外部署
- **自动端口管理** — 端口冲突时自动切换备用端口并通知用户
- **局域网即用** — 自动配置 Windows 防火墙，同一网络下的设备可直接拉流
- **音视频同步** — 可选麦克风音频一同推流
- **高性能模式** — FFmpeg 直接采集摄像头（DirectShow），无 Python 管道瓶颈
- **实时预览** — 本地画面叠加时间戳，方便测量端到端延迟

## 使用场景

| 场景 | 说明 |
|------|------|
| **无人机图传** | 将机载摄像头画面通过 RTSP 实时传输到地面站，UDP 模式延迟极低 |
| **远程监控** | 把 USB/IP 摄像头变成网络流，多端同时拉流查看 |
| **直播推流源** | 作为 OBS / VLC 等工具的 RTSP 输入源 |
| **教学演示** | 将摄像头画面实时分享给局域网内多个学生终端 |

## 快速开始

### 环境要求

- Windows 10 / 11
- Python 3.10+

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动

双击 `run.bat` 或命令行运行：

```bash
python main.py
```

首次启动时，程序会自动安装 FFmpeg 和 MediaMTX（优先从 `packages/` 目录离线安装，否则联网下载）。

### 3. 推流

1. 选择摄像头
2. 配置分辨率、帧率、编码格式、传输协议
3. 点击 **「开始推流」**
4. 复制推流地址，在其他设备上拉流

### 4. 拉流

在同一局域网的任意设备上：

```bash
# VLC（UDP，低延迟）
vlc rtsp://<本机IP>:8554/live

# VLC（TCP，稳定优先）
vlc --rtsp-tcp rtsp://<本机IP>:8554/live

# ffplay
ffplay rtsp://<本机IP>:8554/live
```

## 项目结构

```
CamStream/
├── main.py                 # 入口
├── run.bat                 # 双击启动（免终端）
├── requirements.txt
├── split_packages.py       # 大文件分片工具（Git 友好）
├── packages/               # FFmpeg & MediaMTX 安装包
└── src/
    ├── main_window.py      # PyQt6 主界面
    ├── camera.py           # 摄像头枚举与采集
    ├── audio.py            # 音频设备枚举
    ├── rtsp_sender.py      # FFmpeg RTSP 推流引擎
    ├── ffmpeg_installer.py # FFmpeg 自动安装
    ├── mediamtx_server.py  # MediaMTX 服务管理
    ├── packages_utils.py   # 安装包分片合并工具
    └── config.py           # 配置管理
```

## 技术栈

| 组件 | 用途 |
|------|------|
| **PyQt6** | GUI 界面 |
| **OpenCV** | 摄像头采集与预览 |
| **FFmpeg** | 视频编码与 RTSP 推流 |
| **MediaMTX** | 轻量级 RTSP/RTMP 流媒体服务器 |

## 常见问题

<details>
<summary><b>推流地址在哪里查看？</b></summary>

启动推流后，界面顶部显示完整的 RTSP 地址，点击「复制推流地址」即可分享给其他设备。将 `127.0.0.1` 替换为本机局域网 IP 即可在其他设备拉流。
</details>

<details>
<summary><b>如何降低延迟？</b></summary>

- 传输协议选择 **UDP**
- 编码格式选择 **H.264 (NVENC GPU)**（需 NVIDIA 显卡）
- 勾选「高性能模式」
- 适当降低分辨率和码率
</details>

<details>
<summary><b>局域网其他设备无法拉流？</b></summary>

程序会自动尝试配置 Windows 防火墙放行。若失败（非管理员权限），请手动放行对应端口的 TCP+UDP 入站规则，或以管理员身份运行程序。
</details>

<details>
<summary><b>提示端口被占用？</b></summary>

程序会自动尝试备用端口（8554 → 18554 → 28554 → 38554），并弹窗通知新地址。无需手动干预。
</details>

## 参与贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 发起 Pull Request

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

## 作者与论坛

- 作者主页：[Bilibili](https://space.bilibili.com/1765875510)
- 论坛：[www.xiaorin.cn](https://www.xiaorin.cn)

## WinUI 3 安装与便携版本

WinUI 3 版本将提供标准安装程序和免安装 ZIP；详细说明与构建方式见 [README-WinUI.md](README-WinUI.md)。安装/便携包包含应用和 FFmpeg/MediaMTX，Windows App Runtime 首次使用时按提示安装。

