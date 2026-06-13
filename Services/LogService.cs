using System.IO;
using System.Text;

namespace ShelterPetViewer.Services;

public static class LogService
{
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
            var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} [{level}] {message}{Environment.NewLine}";
            File.AppendAllText(LogPath, line);
        }
    }
}
