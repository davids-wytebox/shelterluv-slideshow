namespace ShelterPetViewer.Services;

internal static class PhotoUrlValidator
{
    private const int MaxDownloadBytes = 20 * 1024 * 1024;

    private static readonly HashSet<string> AllowedHosts = new(StringComparer.OrdinalIgnoreCase)
    {
        "cdn.shelterluv.com",
        "shelterluv.com",
        "new.shelterluv.com",
        "new-s3.shelterluv.com",
        "www.shelterluv.com"
    };

    public static int MaxBytes => MaxDownloadBytes;

    public static bool IsAllowed(string? url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return false;

        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return false;

        if (uri.Scheme is not "https" and not "http")
            return false;

        if (uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
            uri.Host.StartsWith("127.", StringComparison.Ordinal) ||
            uri.Host.StartsWith("10.", StringComparison.Ordinal) ||
            uri.Host.StartsWith("192.168.", StringComparison.Ordinal))
        {
            return false;
        }

        return AllowedHosts.Contains(uri.Host) ||
               uri.Host.EndsWith(".shelterluv.com", StringComparison.OrdinalIgnoreCase);
    }

    public static bool TryGetImageExtension(ReadOnlySpan<byte> bytes, out string extension)
    {
        extension = "";

        if (LooksLikeJpeg(bytes))
        {
            extension = "jpg";
            return true;
        }

        if (LooksLikePng(bytes))
        {
            extension = "png";
            return true;
        }

        return false;
    }

    private static bool LooksLikeJpeg(ReadOnlySpan<byte> bytes) =>
        bytes.Length >= 3 &&
        bytes[0] == 0xFF &&
        bytes[1] == 0xD8 &&
        bytes[2] == 0xFF;

    private static bool LooksLikePng(ReadOnlySpan<byte> bytes) =>
        bytes.Length >= 8 &&
        bytes[0] == 0x89 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x4E &&
        bytes[3] == 0x47 &&
        bytes[4] == 0x0D &&
        bytes[5] == 0x0A &&
        bytes[6] == 0x1A &&
        bytes[7] == 0x0A;
}
