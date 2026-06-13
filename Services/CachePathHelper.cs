using System.IO;
using ShelterPetViewer.Models;

namespace ShelterPetViewer.Services;

internal static class CachePathHelper
{
    private static readonly HashSet<string> ReservedNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    };

    public static bool TrySanitizeId(string? uniqueId, out string sanitized)
    {
        sanitized = "";
        if (string.IsNullOrWhiteSpace(uniqueId))
            return false;

        sanitized = string.Concat(uniqueId.Where(ch => !Path.GetInvalidFileNameChars().Contains(ch)));
        if (string.IsNullOrWhiteSpace(sanitized))
            return false;

        if (sanitized is "." or "..")
            return false;

        if (ReservedNames.Contains(sanitized))
            return false;

        return true;
    }

    public static bool IsUnderRoot(string fullPath, string rootDirectory)
    {
        var normalizedRoot = Path.GetFullPath(rootDirectory)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        var normalizedPath = Path.GetFullPath(fullPath);
        return normalizedPath.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase);
    }

    public static string? ResolveAnimalDirectory(string cacheRoot, ViewMode mode, string sanitizedId)
    {
        var modeDir = Path.Combine(cacheRoot, mode.ToString().ToLowerInvariant());
        var animalDir = Path.GetFullPath(Path.Combine(modeDir, sanitizedId));
        return IsUnderRoot(animalDir, cacheRoot) ? animalDir : null;
    }
}
