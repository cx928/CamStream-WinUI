# CamStream WinUI 3

CamStream 将摄像头画面转换为局域网 RTSP 视频流。该目录包含原 Python/PyQt 版本与原生 C# / WinUI 3 版本。

## WinUI 3 功能

- 摄像头、麦克风选择
- 分辨率、帧率、H.264/H.265/NVIDIA NVENC、UDP/TCP 配置
- FFmpeg DirectShow 采集与 RTSP 推流
- MediaMTX 服务启动和备用端口选择
- 本机 RTSP 回读预览、RTSP 地址复制
- 运行组件自动准备

## 版本与运行

发布页提供两种 x64 版本：

- **安装版**：运行 `CamStream-Setup-1.0.0.exe`，快捷方式创建在开始菜单和桌面。
- **免安装版**：解压 `CamStream-Portable-1.0.0.zip` 后运行 `CamStream.WinUI.exe`，不写入注册表，可放在 U 盘目录。

两个版本均包含自包含 .NET/WinUI 发布文件、FFmpeg、MediaMTX。离线安装版需先在联网时安装一次 Windows App Runtime 1.6；在线安装版由安装器自动下载并安装该运行时。首次启动和推流无需再下载 FFmpeg/MediaMTX。

系统要求：Windows 10 1809+ x64。局域网其他设备拉流时，将 `127.0.0.1` 替换成运行本程序的电脑局域网 IP。防火墙规则需按需手动允许所选 RTSP 端口。

## 作者与论坛

- 作者主页：[Bilibili](https://space.bilibili.com/1765875510)
- 论坛：[www.xiaorin.cn](https://www.xiaorin.cn)

## 开发与构建

使用 .NET SDK 8.0.425 和 Visual Studio 2022 / Windows App SDK，在 x64 下构建：

```powershell
.\scripts\publish.ps1
```

脚本会生成 `artifacts\CamStream-Setup-1.0.0.exe` 和 `artifacts\CamStream-Portable-1.0.0.zip`。构建前需要安装 Inno Setup 6，并在 `tools\ffmpeg` 放入 FFmpeg Essentials 的可执行文件与 DLL，在 `tools\mediamtx\mediamtx.exe` 放入 MediaMTX。

原 Python 版运行方式见上方原始 README 的快速开始部分。
