using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using Windows.ApplicationModel.DataTransfer;
using Windows.Devices.Enumeration;
using Windows.Media.Devices;
using Windows.Storage.Streams;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.UI;

namespace CamStream;

public sealed partial class MainWindow : Window
{
    private const string MediaMtxVersion = "1.16.2";
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromMinutes(10) };
    private readonly string _dataDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CamStream");
    private Process? _mediaMtx;
    private Process? _ffmpeg;
    private Process? _preview;
    private CancellationTokenSource? _previewCts;
    private bool _initialScanStarted;
    private bool _isStarting;
    private bool _runtimeChecked;
    private int _activePort;

    public MainWindow()
    {
        InitializeComponent();
        Title = "CamStream";
        Activated += OnActivated;
        Closed += OnClosed;
    }

    private async void OnActivated(object sender, WindowActivatedEventArgs e)
    {
        if (_initialScanStarted) return;
        _initialScanStarted = true;
        if (!_runtimeChecked)
        {
            _runtimeChecked = true;
            if (!await EnsureWindowsAppRuntimeAsync()) return;
        }
        try { await RefreshDevicesAsync(); }
        catch (Exception ex) { HintText.Text = $"设备扫描失败：{ex.Message}"; }
    }

    private void OnClosed(object sender, WindowEventArgs e)
    {
        StopProcesses();
        _http.Dispose();
    }

    private async Task<bool> EnsureWindowsAppRuntimeAsync()
    {
        if (!IsWindowsAppRuntimeInstalled())
        {
            var installer = Path.Combine(AppContext.BaseDirectory, "WindowsAppRuntimeInstall-x64.exe");
            if (!File.Exists(installer))
            {
                await ShowMessageAsync("缺少 Windows App Runtime 1.6，安装程序文件也未找到。请重新下载安装包。", "无法启动 CamStream");
                return false;
            }
            try
            {
                var process = StartProcess(installer, ["/quiet", "/norestart"], AppContext.BaseDirectory, false);
                await process.WaitForExitAsync();
                process.Dispose();
            }
            catch (Exception ex)
            {
                await ShowMessageAsync($"无法安装 Windows App Runtime：{ex.Message}", "运行时安装失败");
                return false;
            }
            if (!IsWindowsAppRuntimeInstalled())
            {
                await ShowMessageAsync("Windows App Runtime 安装未完成。请重试运行时安装程序。", "运行时安装失败");
                return false;
            }
            var executable = Environment.ProcessPath;
            if (!string.IsNullOrWhiteSpace(executable))
                Process.Start(new ProcessStartInfo(executable) { UseShellExecute = true });
            Close();
            return false;
        }
        return true;
    }

    private static bool IsWindowsAppRuntimeInstalled()
    {
        using var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64");
        if (key?.GetValue("Version") is not null) return true;
        using var userKey = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64");
        return userKey?.GetValue("Version") is not null;
    }

    private async Task RefreshDevicesAsync()
    {
        RefreshButton.IsEnabled = false;
        CameraCombo.Items.Clear();
        AudioCombo.Items.Clear();
        CameraCombo.PlaceholderText = "正在扫描摄像头…";
        try
        {
            var cameras = await DeviceInformation.FindAllAsync(DeviceClass.VideoCapture);
            foreach (var device in cameras) CameraCombo.Items.Add(device);
            CameraCombo.DisplayMemberPath = nameof(DeviceInformation.Name);
            CameraCombo.PlaceholderText = cameras.Count == 0 ? "没有找到摄像头" : "选择摄像头";
            if (CameraCombo.Items.Count > 0) CameraCombo.SelectedIndex = 0;

            AudioCombo.Items.Add(new ComboBoxItem { Content = "不推送音频", Tag = "" });
            var microphones = await DeviceInformation.FindAllAsync(MediaDevice.GetAudioCaptureSelector());
            foreach (var device in microphones)
                AudioCombo.Items.Add(new ComboBoxItem { Content = device.Name, Tag = device.Name });
            AudioCombo.SelectedIndex = 0;
            SetStatus(cameras.Count > 0 ? "摄像头已就绪" : "未发现摄像头", cameras.Count > 0);
        }
        catch (Exception ex)
        {
            CameraCombo.PlaceholderText = "设备扫描失败";
            SetStatus("设备扫描失败", false);
            HintText.Text = $"无法扫描音视频设备：{ex.Message}";
        }
        finally { RefreshButton.IsEnabled = true; }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshDevicesAsync();

    private async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isStarting) return;
        if (_ffmpeg is { HasExited: false })
        {
            StopProcesses();
            StartButton.Content = "开始推流";
            StartButton.Background = BlueBrush();
            PreviewBadge.Text = "未连接";
            PreviewText.Text = "开始推流后，画面将在此显示";
            PreviewImage.Visibility = Visibility.Collapsed;
            PreviewPlaceholder.Visibility = Visibility.Visible;
            SetStatus("已停止", false);
            return;
        }

        if (CameraCombo.SelectedItem is not DeviceInformation camera)
        {
            await ShowMessageAsync("请先连接并选择一个摄像头。", "没有选择摄像头");
            return;
        }

        _isStarting = true;
        StartButton.IsEnabled = false;
        StartButton.Content = "正在准备组件…";
        SetStatus("正在准备…", false);
        try
        {
            var tools = await EnsureToolsAsync();
            Directory.CreateDirectory(_dataDirectory);
            _activePort = FindAvailablePort();
            var configPath = Path.Combine(_dataDirectory, "mediamtx.yml");
            var config = $"logLevel: warn\nwriteQueueSize: 1024\nrtsp: true\nrtspAddress: :{_activePort}\nrtspTransports: [udp, tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\npaths:\n  all_others:\n";
            await File.WriteAllTextAsync(configPath, config, new UTF8Encoding(false));

            StartButton.Content = "正在启动 RTSP 服务…";
            _mediaMtx = StartProcess(tools.MediaMtx, [configPath], _dataDirectory, redirectStderr: true);
            _ = ObserveErrorsAsync(_mediaMtx, "MediaMTX");
            await Task.Delay(800);
            if (_mediaMtx.HasExited) throw new InvalidOperationException("MediaMTX 服务启动失败。请稍后重试或检查端口占用。");

            var audioName = (AudioCombo.SelectedItem as ComboBoxItem)?.Tag as string;
            if (string.IsNullOrWhiteSpace(audioName)) audioName = null;
            var widthHeight = SelectedTag(ResolutionCombo, "1920x1080").Split('x');
            if (widthHeight.Length != 2) throw new InvalidOperationException("分辨率选项无效。");
            var fps = SelectedTag(FpsCombo, "30");
            var codec = SelectedTag(CodecCombo, "libx264");
            var transport = SelectedTag(TransportCombo, "udp");
            var url = $"rtsp://127.0.0.1:{_activePort}/live";
            UrlBox.Text = url;
            var arguments = BuildStreamArguments(camera.Name, audioName, widthHeight[0], widthHeight[1], fps, codec, transport, url);

            StartButton.Content = "正在连接摄像头…";
            _ffmpeg = StartProcess(tools.Ffmpeg, arguments, _dataDirectory, redirectStderr: true);
            var streamProcess = _ffmpeg;
            streamProcess.Exited += (_, _) => DispatcherQueue.TryEnqueue(() =>
            {
                if (!ReferenceEquals(_ffmpeg, streamProcess)) return;
                StartButton.Content = "开始推流";
                StartButton.Background = BlueBrush();
                PreviewBadge.Text = "已断开";
                SetStatus("推流进程已退出", false);
            });
            _ = ObserveErrorsAsync(streamProcess, "FFmpeg");
            await Task.Delay(1100);
            if (_ffmpeg.HasExited)
            {
                var advice = codec == "h264_nvenc" ? "请确认电脑有可用的 NVIDIA 显卡和驱动。" : "请尝试较低分辨率或 H.264 编码。";
                throw new InvalidOperationException($"FFmpeg 无法打开摄像头或连接 RTSP 服务。{advice}");
            }

            StartButton.Content = "停止推流";
            StartButton.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Color.FromArgb(255, 205, 67, 67));
            PreviewBadge.Text = "正在连接";
            PreviewText.Text = "等待视频画面…";
            SetStatus($"推流中 · :{_activePort}", true);
            HintText.Text = "推流已启动；局域网设备请把 127.0.0.1 替换为本机局域网 IP。";
            StartPreview(tools.Ffmpeg, url);
        }
        catch (Exception ex)
        {
            StopProcesses();
            StartButton.Content = "开始推流";
            StartButton.Background = BlueBrush();
            PreviewBadge.Text = "启动失败";
            SetStatus("启动失败", false);
            HintText.Text = ex.Message;
            await ShowMessageAsync(ex.Message, "启动推流失败");
        }
        finally
        {
            _isStarting = false;
            StartButton.IsEnabled = true;
        }
    }

    private async Task<(string Ffmpeg, string MediaMtx)> EnsureToolsAsync()
    {
        var toolsDirectory = Path.Combine(_dataDirectory, "tools");
        Directory.CreateDirectory(toolsDirectory);
        var ffmpegPath = Path.Combine(toolsDirectory, "ffmpeg.exe");
        var mediamtxPath = Path.Combine(toolsDirectory, "mediamtx.exe");
        var bundledTools = Path.Combine(AppContext.BaseDirectory, "tools");
        var bundledFfmpeg = Path.Combine(bundledTools, "ffmpeg", "ffmpeg.exe");
        var bundledMediaMtx = Path.Combine(bundledTools, "mediamtx", "mediamtx.exe");
        if (!File.Exists(ffmpegPath) && File.Exists(Path.Combine(bundledTools, "ffmpeg.exe")))
            File.Copy(Path.Combine(bundledTools, "ffmpeg.exe"), ffmpegPath, true);
        else if (!File.Exists(ffmpegPath) && File.Exists(bundledFfmpeg))
            File.Copy(bundledFfmpeg, ffmpegPath, true);
        if (!File.Exists(mediamtxPath) && File.Exists(Path.Combine(bundledTools, "mediamtx.exe")))
            File.Copy(Path.Combine(bundledTools, "mediamtx.exe"), mediamtxPath, true);
        else if (!File.Exists(mediamtxPath) && File.Exists(bundledMediaMtx))
            File.Copy(bundledMediaMtx, mediamtxPath, true);

        if (!File.Exists(ffmpegPath))
        {
            var systemFfmpeg = FindOnPath("ffmpeg.exe");
            if (systemFfmpeg is not null) ffmpegPath = systemFfmpeg;
            else
            {
                HintText.Text = "首次使用：正在下载 FFmpeg（约数十 MB）…";
                var zipPath = Path.Combine(toolsDirectory, "ffmpeg.zip");
                try
                {
                    await DownloadFileAsync("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", zipPath);
                    using var archive = ZipFile.OpenRead(zipPath);
                    var ffmpegEntry = archive.Entries.FirstOrDefault(x => Path.GetFileName(x.FullName).Equals("ffmpeg.exe", StringComparison.OrdinalIgnoreCase))
                        ?? throw new InvalidDataException("FFmpeg 压缩包中未找到 ffmpeg.exe。");
                    ffmpegEntry.ExtractToFile(ffmpegPath, true);
                    var binDirectory = Path.GetDirectoryName(ffmpegEntry.FullName);
                    if (!string.IsNullOrEmpty(binDirectory))
                    {
                        foreach (var entry in archive.Entries.Where(x => x.FullName.StartsWith(binDirectory.TrimEnd('/') + "/", StringComparison.OrdinalIgnoreCase)))
                        {
                            if (entry.FullName.EndsWith('/')) continue;
                            var name = Path.GetFileName(entry.FullName);
                            if (name.Length == 0 || name.Equals("ffmpeg.exe", StringComparison.OrdinalIgnoreCase)) continue;
                            entry.ExtractToFile(Path.Combine(toolsDirectory, name), true);
                        }
                    }
                }
                finally { TryDelete(zipPath); }
            }
        }

        if (!File.Exists(mediamtxPath))
        {
            HintText.Text = $"正在下载 MediaMTX {MediaMtxVersion}…";
            var zipPath = Path.Combine(toolsDirectory, "mediamtx.zip");
            var url = $"https://github.com/bluenviron/mediamtx/releases/download/v{MediaMtxVersion}/mediamtx_v{MediaMtxVersion}_windows_amd64.zip";
            try
            {
                await DownloadFileAsync(url, zipPath);
                using var archive = ZipFile.OpenRead(zipPath);
                var entry = archive.Entries.FirstOrDefault(x => Path.GetFileName(x.FullName).Equals("mediamtx.exe", StringComparison.OrdinalIgnoreCase))
                    ?? throw new InvalidDataException("MediaMTX 压缩包中未找到 mediamtx.exe。");
                entry.ExtractToFile(mediamtxPath, true);
            }
            finally { TryDelete(zipPath); }
        }

        if (!File.Exists(ffmpegPath)) throw new FileNotFoundException("FFmpeg 未能安装。请检查网络后重试。", ffmpegPath);
        if (!File.Exists(mediamtxPath)) throw new FileNotFoundException("MediaMTX 未能安装。请检查网络后重试。", mediamtxPath);
        return (ffmpegPath, mediamtxPath);
    }

    private async Task DownloadFileAsync(string url, string destination)
    {
        using var response = await _http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();
        var total = response.Content.Headers.ContentLength;
        await using var input = await response.Content.ReadAsStreamAsync();
        await using var output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None, 65536, true);
        var buffer = new byte[65536];
        long received = 0;
        int count;
        while ((count = await input.ReadAsync(buffer)) > 0)
        {
            await output.WriteAsync(buffer.AsMemory(0, count));
            received += count;
            if (total is > 0)
            {
                var percent = Math.Clamp((int)(received * 100 / total.Value), 0, 100);
                DispatcherQueue.TryEnqueue(() => HintText.Text = $"正在下载运行组件… {percent}%");
            }
        }
        await output.FlushAsync();
    }

    private static int FindAvailablePort()
    {
        foreach (var port in new[] { 8554, 18554, 28554, 38554 })
        {
            try
            {
                using var listener = new TcpListener(IPAddress.Any, port);
                listener.Start();
                return port;
            }
            catch (SocketException) { }
        }
        throw new InvalidOperationException("RTSP 默认端口 8554、18554、28554、38554 均不可用。");
    }

    private static IReadOnlyList<string> BuildStreamArguments(string camera, string? audio, string width, string height, string fps, string codec, string transport, string url)
    {
        var input = "video=" + DshowName(camera);
        if (!string.IsNullOrWhiteSpace(audio)) input += ":audio=" + DshowName(audio);
        var args = new List<string> { "-hide_banner", "-loglevel", "warning", "-f", "dshow", "-rtbufsize", "128M", "-framerate", fps, "-video_size", $"{width}x{height}", "-i", input, "-map", "0:v:0" };
        if (!string.IsNullOrWhiteSpace(audio)) args.AddRange(["-map", "0:a:0"]);
        args.AddRange(["-c:v", codec, "-pix_fmt", "yuv420p", "-b:v", "4000k", "-g", fps]);
        switch (codec)
        {
            case "libx264": args.AddRange(["-preset", "ultrafast", "-tune", "zerolatency", "-x264opts", "rc-lookahead=0"]); break;
            case "libx265": args.AddRange(["-preset", "ultrafast", "-x265-params", "rc-lookahead=0"]); break;
            case "h264_nvenc": args.AddRange(["-preset", "p1", "-tune", "ull", "-delay", "0"]); break;
        }
        if (!string.IsNullOrWhiteSpace(audio)) args.AddRange(["-c:a", "aac", "-b:a", "128k", "-ar", "44100"]);
        args.AddRange(["-f", "rtsp", "-rtsp_transport", transport, "-muxdelay", "0.1", url]);
        return args;
    }

    private static string DshowName(string name) => "\"" + name.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

    private void StartPreview(string ffmpegPath, string url)
    {
        _previewCts = new CancellationTokenSource();
        var args = new[] { "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", url, "-an", "-vf", "fps=5,scale=640:-1", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1" };
        _preview = StartProcess(ffmpegPath, args, _dataDirectory, redirectStderr: true, redirectStdout: true);
        _ = ObserveErrorsAsync(_preview, "预览");
        _ = ReadPreviewFramesAsync(_preview, _previewCts.Token);
    }

    private async Task ReadPreviewFramesAsync(Process process, CancellationToken cancellationToken)
    {
        try
        {
            var stream = process.StandardOutput.BaseStream;
            var buffer = new byte[32768];
            using var frame = new MemoryStream();
            var active = false;
            var previous = -1;
            while (!cancellationToken.IsCancellationRequested)
            {
                var count = await stream.ReadAsync(buffer, cancellationToken);
                if (count == 0) break;
                for (var i = 0; i < count; i++)
                {
                    var current = buffer[i];
                    if (!active && previous == 0xFF && current == 0xD8)
                    {
                        frame.SetLength(0);
                        frame.WriteByte(0xFF);
                        frame.WriteByte(0xD8);
                        active = true;
                    }
                    else if (active)
                    {
                        frame.WriteByte((byte)current);
                        if (previous == 0xFF && current == 0xD9)
                        {
                            await ShowPreviewFrameAsync(frame.ToArray());
                            active = false;
                        }
                    }
                    previous = current;
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (ObjectDisposedException) { }
        catch (IOException) { }
    }

    private async Task ShowPreviewFrameAsync(byte[] jpeg)
    {
        await DispatcherQueue.EnqueueAsync(async () =>
        {
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream.GetOutputStreamAt(0)))
            {
                writer.WriteBytes(jpeg);
                await writer.StoreAsync();
                await writer.FlushAsync();
                writer.DetachStream();
            }
            stream.Seek(0);
            var bitmap = new BitmapImage();
            await bitmap.SetSourceAsync(stream);
            PreviewImage.Source = bitmap;
            PreviewImage.Visibility = Visibility.Visible;
            PreviewPlaceholder.Visibility = Visibility.Collapsed;
            PreviewBadge.Text = "预览中";
        });
    }

    private async Task ObserveErrorsAsync(Process process, string source)
    {
        try
        {
            while (!process.HasExited)
            {
                var line = await process.StandardError.ReadLineAsync();
                if (line is null) break;
                if (Regex.IsMatch(line, "(error|failed|refused|not found|invalid)", RegexOptions.IgnoreCase))
                    DispatcherQueue.TryEnqueue(() => HintText.Text = $"{source}: {line}");
            }
        }
        catch (InvalidOperationException) { }
        catch (IOException) { }
    }

    private static Process StartProcess(string file, IEnumerable<string> arguments, string workingDirectory, bool redirectStderr, bool redirectStdout = false)
    {
        var info = new ProcessStartInfo
        {
            FileName = file,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = redirectStderr,
            RedirectStandardOutput = redirectStdout
        };
        foreach (var argument in arguments) info.ArgumentList.Add(argument);
        var process = new Process { StartInfo = info, EnableRaisingEvents = true };
        process.Start();
        return process;
    }

    private static string SelectedTag(ComboBox combo, string fallback) =>
        combo.SelectedItem is ComboBoxItem item && item.Tag is string value ? value : fallback;

    private void StopProcesses()
    {
        _previewCts?.Cancel();
        StopProcess(_preview);
        StopProcess(_ffmpeg);
        StopProcess(_mediaMtx);
        _preview = null;
        _ffmpeg = null;
        _mediaMtx = null;
    }

    private static void StopProcess(Process? process)
    {
        try
        {
            if (process is { HasExited: false })
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(1500);
            }
        }
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception) { }
        finally { process?.Dispose(); }
    }

    private void SetStatus(string text, bool ready)
    {
        StatusText.Text = text;
        StatusText.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(
            Color.FromArgb(255, ready ? (byte)33 : (byte)160, ready ? (byte)133 : (byte)112, ready ? (byte)87 : (byte)67));
    }

    private static Microsoft.UI.Xaml.Media.SolidColorBrush BlueBrush() =>
        new(Color.FromArgb(255, 45, 106, 227));

    private async void CopyButton_Click(object sender, RoutedEventArgs e)
    {
        var data = new DataPackage();
        data.SetText(UrlBox.Text);
        Clipboard.SetContent(data);
        HintText.Text = "RTSP 地址已复制到剪贴板。";
        await Task.CompletedTask;
    }

    private async Task ShowMessageAsync(string message, string title)
    {
        var dialog = new ContentDialog { Title = title, Content = message, CloseButtonText = "确定", XamlRoot = Content.XamlRoot };
        await dialog.ShowAsync();
    }

    private static string? FindOnPath(string name)
    {
        foreach (var folder in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try
            {
                var candidate = Path.Combine(folder.Trim('"'), name);
                if (File.Exists(candidate)) return candidate;
            }
            catch (ArgumentException) { }
        }
        return null;
    }

    private static void TryDelete(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}

internal static class DispatcherQueueExtensions
{
    public static Task EnqueueAsync(this DispatcherQueue queue, Func<Task> action)
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!queue.TryEnqueue(async () =>
        {
            try { await action(); completion.SetResult(); }
            catch (Exception ex) { completion.SetException(ex); }
        })) completion.SetException(new InvalidOperationException("UI dispatcher is unavailable."));
        return completion.Task;
    }
}
