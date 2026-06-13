using System.IO;

namespace ShelterPetViewer.Services;

internal static class AtomicFileHelper
{
    public static void WriteAllText(string path, string contents)
    {
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory))
            Directory.CreateDirectory(directory);

        var tempPath = path + ".tmp";
        File.WriteAllText(tempPath, contents);
        File.Move(tempPath, path, overwrite: true);
    }

    public static async Task WriteAllTextAsync(string path, string contents, CancellationToken cancellationToken = default)
    {
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory))
            Directory.CreateDirectory(directory);

        var tempPath = path + ".tmp";
        await File.WriteAllTextAsync(tempPath, contents, cancellationToken);
        File.Move(tempPath, path, overwrite: true);
    }

    public static async Task WriteAllBytesAsync(string path, byte[] bytes, CancellationToken cancellationToken = default)
    {
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory))
            Directory.CreateDirectory(directory);

        var tempPath = path + ".tmp";
        await File.WriteAllBytesAsync(tempPath, bytes, cancellationToken);
        File.Move(tempPath, path, overwrite: true);
    }
}
