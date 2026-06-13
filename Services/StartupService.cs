using Microsoft.Win32;

namespace ShelterPetViewer.Services;

public static class StartupService
{
    private const string RunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string AppName = "ShelterPetViewer";

    public static bool IsEnabled()
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, writable: false);
        return key?.GetValue(AppName) is string;
    }

    public static void SetEnabled(bool enabled)
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, writable: true)
            ?? Registry.CurrentUser.CreateSubKey(RunKeyPath, writable: true);

        if (enabled)
        {
            var path = Environment.ProcessPath;
            if (string.IsNullOrWhiteSpace(path))
            {
                LogService.Error("Cannot enable startup: process path is unavailable.");
                return;
            }

            key.SetValue(AppName, $"\"{path}\"");
        }
        else
            key.DeleteValue(AppName, throwOnMissingValue: false);
    }
}
