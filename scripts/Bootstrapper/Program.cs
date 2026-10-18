using System.Diagnostics;
using System.Reflection;
using Microsoft.Win32;

internal static class Program
{
    [STAThread]
    private static int Main()
    {
        var temp = Path.Combine(Path.GetTempPath(), "CamStreamSetup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            Extract("CamStream.Msi", Path.Combine(temp, "CamStream.msi"));
            Extract("CamStream.Runtime", Path.Combine(temp, "WindowsAppRuntimeInstall-x64.exe"));
            if (!RuntimeInstalled())
            {
                var runtime = Process.Start(new ProcessStartInfo(Path.Combine(temp, "WindowsAppRuntimeInstall-x64.exe"), "/quiet /norestart") { UseShellExecute = true });
                runtime?.WaitForExit();
                if (!RuntimeInstalled()) return Fail("Windows App Runtime 安装失败，请重试。");
            }
            var msi = Process.Start(new ProcessStartInfo("msiexec.exe", $"/i \"{Path.Combine(temp, "CamStream.msi")}\" /passive") { UseShellExecute = true });
            msi?.WaitForExit();
            return msi?.ExitCode ?? 1;
        }
        catch (Exception ex) { return Fail(ex.Message); }
        finally { try { Directory.Delete(temp, true); } catch { } }
    }

    private static void Extract(string resourceName, string path)
    {
        using var input = Assembly.GetExecutingAssembly().GetManifestResourceStream(resourceName) ?? throw new FileNotFoundException(resourceName);
        using var output = File.Create(path);
        input.CopyTo(output);
    }

    private static bool RuntimeInstalled()
    {
        using var machine = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64");
        if (machine?.GetValue("Version") is not null) return true;
        using var user = Registry.CurrentUser.OpenSubKey(@"SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64");
        return user?.GetValue("Version") is not null;
    }

    private static int Fail(string message) { Console.Error.WriteLine(message); return 1; }
}
