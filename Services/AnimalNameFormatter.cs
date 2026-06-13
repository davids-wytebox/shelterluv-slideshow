using System.Globalization;
using System.Text.RegularExpressions;

namespace ShelterPetViewer.Services;

public static class AnimalNameFormatter
{
    private static readonly Regex IdSuffixRegex = new(
        @"\s+\*{0,2}\s*([A-Z]\d{4,6})\*{0,2}(?:\s+\((?<note>[^)]+)\))?\s*$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public static (string DisplayName, string? AnimalId, string? Note) Parse(string fullName)
    {
        var trimmed = fullName.Trim();
        var match = IdSuffixRegex.Match(trimmed);
        if (!match.Success)
            return (CleanDisplayName(trimmed), null, null);

        var displayName = CleanDisplayName(trimmed[..match.Index]);
        var animalId = match.Groups[1].Value;
        var note = match.Groups["note"].Success ? match.Groups["note"].Value : null;
        return (displayName, animalId, note);
    }

    public static string FormatCardText(string? animalId, string? note, string description)
    {
        var headerParts = new List<string>();
        if (!string.IsNullOrWhiteSpace(animalId))
            headerParts.Add(animalId);
        if (!string.IsNullOrWhiteSpace(note))
            headerParts.Add($"({note})");

        var header = string.Join(" ", headerParts);
        var body = DescriptionFormatter.Normalize(description);

        if (string.IsNullOrWhiteSpace(header))
            return body;
        if (string.IsNullOrWhiteSpace(body))
            return header;

        return $"{header}{Environment.NewLine}{body}";
    }

    private static string CleanDisplayName(string value) =>
        value.Trim().TrimEnd('*').Trim();

    public static string ToTitleCase(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return value;

        return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.ToLowerInvariant());
    }
}
