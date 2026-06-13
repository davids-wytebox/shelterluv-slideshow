using System.Net;
using System.Text.RegularExpressions;

namespace ShelterPetViewer.Services;

public static class DescriptionFormatter
{
    public static string FromHtml(string html)
    {
        var text = html;
        text = Regex.Replace(text, @"<br\s*/?>", "\n", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"</p>", "\n", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"<li[^>]*>", "• ", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"<[^>]+>", string.Empty);
        text = WebUtility.HtmlDecode(text);
        return Normalize(text);
    }

    public static string Normalize(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
            return string.Empty;

        var lines = text
            .Split(['\r', '\n'])
            .Select(line => line.Trim())
            .Where(line => line.Length > 0);

        return string.Join(Environment.NewLine, lines);
    }
}
