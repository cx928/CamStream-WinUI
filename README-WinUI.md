# CamStream for WinUI 3

原 CamStream（Python/PyQt）项目的原生 Windows 桌面重构版。新版本使用 C#、WinUI 3 和 Windows App SDK，保留原版 RTSP 推流目标，并采用简洁的双栏操作界面。

## 功能

- 自动枚举摄像头和麦克风
- 选择视频分辨率、帧率、H.264/H.265/NVIDIA NVENC 编码与 UDP/TCP 传输
- 通过 FFmpeg DirectShow 同步采集摄像头和可选麦克风
- 启动/停止 MediaMTX RTSP 服务与 FFmpeg 推流
- 默认端口 8554 被占用时依次尝试 18554、28554、38554
- 从本机 RTSP 服务回读视频并在窗口预览
- 自动从 Gyan.dev 获取 FFmpeg Essentials，MediaMTX 从官方 GitHub Release 下载
- 安装到 `%LOCALAPPDATA%\\CamStream\\tools`，不要求管理员权限
- 复制 RTSP 地址；关闭程序时停止其启动的 FFmpeg/MediaMTX 进程

## 运行与构建

- Windows 10 1809+（建议 Windows 11），x64
- .NET 8 SDK、Visual Studio 2022 的 Windows App SDK/WinUI 3 构建组件
- 用 Visual Studio 打开 `CamStream.WinUI.csproj`，选择 x64 并生成

首次推流需要网络连接以下载 FFmpeg 与 MediaMTX。二者下载后保存在当前 Windows 用户的 `%LOCALAPPDATA%\\CamStream\\tools`。FFmpeg Essentials ZIP 中只解压 `bin` 目录文件。

> 此应用是 unpackaged WinUI 3 桌面程序。Windows Defender 防火墙在不同设备策略下表现不同；若其他局域网设备无法连接，请在 Windows 防火墙中手动允许所选 RTSP 端口的入站 TCP/UDP。程序不会静默改写系统防火墙规则。

## 拉流

启动推流后复制地址。局域网其他设备需把地址中的 `127.0.0.1` 替换为运行此应用的电脑的局域网 IPv4 地址，然后在 VLC/OBS/ffplay 中打开。

## 原 Python 版

`main.py`、`src/` 和原有 Python 依赖仍保留。C# WinUI 版入口为 `App.xaml` 与 `MainWindow.xaml`。

## 当前限制

设备兼容性取决于 DirectShow 驱动暴露的名称/格式；所选摄像头分辨率、帧率或 NVENC 不支持时，需调整选择。当前版本没有自动改防火墙规则和安装包/MSIX 发布配置。FFmpeg 下载源为 Gyan.dev FFmpeg Essentials build，MediaMTX 使用项目原有版本 1.16.2。
