using System.Net.Http;
using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;
using ShelterPetViewer.Models;

namespace ShelterPetViewer.Services;

public sealed class ShelterLuvService(HttpClient httpClient)
{
    private const int ShelterId = 38131;
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public async Task<IReadOnlyList<ShelterAnimalSummary>> FetchAnimalsAsync(ViewMode mode, CancellationToken cancellationToken = default)
    {
        var queries = mode == ViewMode.Adoption
            ? new[] { "?animalType=Dog", "?animalType=Cat" }
            : new[] { "?saved_query=5398", "?saved_query=5397" };

        var byId = new Dictionary<string, ShelterAnimalSummary>(StringComparer.OrdinalIgnoreCase);

        foreach (var query in queries)
        {
            var url = $"https://new.shelterluv.com/api/v3/available-animals/{ShelterId}{query}";
            LogService.Info($"Fetching {url}");

            try
            {
                var response = await httpClient.GetAsync(url, cancellationToken);
                response.EnsureSuccessStatusCode();

                var json = await response.Content.ReadAsStringAsync(cancellationToken);
                LogService.Info($"Downloaded {json.Length} bytes for {query}");

                var payload = JsonSerializer.Deserialize<ShelterAnimalListResponse>(json, JsonOptions)
                    ?? new ShelterAnimalListResponse();

                LogService.Info($"Received {payload.Animals.Count} animals for {query}");

                foreach (var animal in payload.Animals)
                {
                    if (!string.IsNullOrWhiteSpace(animal.UniqueId))
                        byId[animal.UniqueId] = animal;
                }
            }
            catch (Exception ex)
            {
                LogService.Error($"Failed fetching animal list for {query}", ex);
                throw;
            }
        }

        return byId.Values.ToList();
    }

    public async Task<ShelterAnimalDetail?> FetchAnimalDetailAsync(string uniqueId, CancellationToken cancellationToken = default)
    {
        try
        {
            var url = $"https://new.shelterluv.com/embed/animal/{Uri.EscapeDataString(uniqueId)}";
            var html = await httpClient.GetStringAsync(url, cancellationToken);

            var match = Regex.Match(html, @":animal=""([^""]+)""", RegexOptions.Singleline);
            if (!match.Success)
            {
                LogService.Error($"Could not find animal JSON in embed page for {uniqueId}");
                return null;
            }

            var json = WebUtility.HtmlDecode(match.Groups[1].Value);
            return JsonSerializer.Deserialize<ShelterAnimalDetail>(json, JsonOptions);
        }
        catch (Exception ex)
        {
            LogService.Error($"Failed to fetch details for {uniqueId}", ex);
            return null;
        }
    }

    public static IReadOnlyList<ShelterPhoto> SelectPhotos(IReadOnlyList<ShelterPhoto> photos, int maxPhotos = 5)
    {
        return photos
            .Where(photo => !IsPromotionalPhoto(photo))
            .OrderBy(photo => photo.OrderColumn)
            .Take(maxPhotos)
            .ToList();
    }

    public static IReadOnlyList<ShelterPhoto> SelectPhotos(ShelterAnimalSummary animal, int maxPhotos = 5) =>
        SelectPhotos(animal.Photos, maxPhotos);

    public static IReadOnlyList<ShelterPhoto> SelectPhotos(ShelterAnimalDetail animal, int maxPhotos = 5) =>
        SelectPhotos(animal.Photos, maxPhotos);

    private static bool IsPromotionalPhoto(ShelterPhoto photo)
    {
        var name = photo.Name.ToLowerInvariant();
        return name.Contains("sponsored") ||
               name.Contains("template") ||
               name.Contains("adoption fee");
    }
}
