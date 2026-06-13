using System.IO;
using System.Text;

namespace ShelterPetViewer.Services;

public static class LogService
{
    private const long MaxLogBytes = 512 * 1024;

    private static readonly object Lock = new();
    private static readonly string LogPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "ShelterPetViewer",
        "log.txt");

    public static string LogFilePath => LogPath;

    public static void Info(string message) => Write("INFO", message);

    public static void Error(string message, Exception? exception = null)
    {
        var builder = new StringBuilder(message);
        if (exception is not null)
        {
            builder.AppendLine();
            builder.Append(exception);
        }

        Write("ERROR", builder.ToString());
    }

    private static void Write(string level, string message)
    {
        lock (Lock)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(LogPath)!);
            RotateIfNeeded();
            var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} [{level}] {message}{Environment.NewLine}";
            File.AppendAllText(LogPath, line);
        }
    }

    private static void RotateIfNeeded()
    {
        if (!File.Exists(LogPath))
            return;

        var info = new FileInfo(LogPath);
        if (info.Length <= MaxLogBytes)
            return;

        var backupPath = Path.Combine(info.DirectoryName!, "log.old.txt");
        if (File.Exists(backupPath))
            File.Delete(backupPath);

        File.Move(LogPath, backupPath);
    }
}
