using System.IO;
using System.Net.Http;
using System.Text;
using ShelterPetViewer.Models;

namespace ShelterPetViewer.Services;

public sealed class CacheService
{
    private readonly ShelterLuvService _shelterLuvService;
    private readonly HttpClient _httpClient;
    private readonly string _cacheRoot;

    public CacheService(ShelterLuvService shelterLuvService, HttpClient httpClient)
    {
        _shelterLuvService = shelterLuvService;
        _httpClient = httpClient;
        _cacheRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "ShelterPetViewer",
            "cache");
        Directory.CreateDirectory(_cacheRoot);
    }

    public string CacheRoot => _cacheRoot;

    public IReadOnlyList<CachedAnimal> LoadCachedAnimals(ViewMode mode)
    {
        var modeDir = GetModeDirectory(mode);
        if (!Directory.Exists(modeDir))
            return [];

        var animals = new List<CachedAnimal>();
        foreach (var animalDir in Directory.GetDirectories(modeDir))
        {
            var infoPath = Path.Combine(animalDir, "info.txt");
            if (!File.Exists(infoPath))
                continue;

            if (!TryParseInfoFile(infoPath, out var animal))
                continue;

            var photos = Directory.GetFiles(animalDir, "*.jpg")
                .OrderBy(filePath => filePath, StringComparer.OrdinalIgnoreCase)
                .ToList();

            if (!photos.Any())
                continue;

            animals.Add(new CachedAnimal
            {
                Id = Path.GetFileName(animalDir),
                Name = animal.Name,
                Species = animal.Species,
                Sex = animal.Sex,
                Weight = animal.Weight,
                Breed = animal.Breed,
                Age = animal.Age,
                PhotoPaths = photos
            });
        }

        return animals;
    }

    public async Task<CacheSyncResult> SyncAsync(ViewMode mode, IProgress<string>? progress = null, CancellationToken cancellationToken = default)
    {
        progress?.Report($"{mode}: Fetching animal list...");
        var remoteAnimals = await _shelterLuvService.FetchAnimalsAsync(mode, cancellationToken);
        var modeDir = GetModeDirectory(mode);
        Directory.CreateDirectory(modeDir);

        var remoteIds = remoteAnimals
            .Select(animal => SanitizeId(animal.UniqueId))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        var removed = 0;
        foreach (var existingDir in Directory.GetDirectories(modeDir))
        {
            var id = Path.GetFileName(existingDir);
            if (!remoteIds.Contains(id))
            {
                Directory.Delete(existingDir, recursive: true);
                removed++;
            }
        }

        var added = 0;
        var updated = 0;

        foreach (var animal in remoteAnimals)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var id = SanitizeId(animal.UniqueId);
            var animalDir = Path.Combine(modeDir, id);
            var isNew = !Directory.Exists(animalDir);

            progress?.Report(isNew ? $"{mode}: Adding {animal.Name}..." : $"{mode}: Updating {animal.Name}...");
            Directory.CreateDirectory(animalDir);

            var detail = await _shelterLuvService.FetchAnimalDetailAsync(animal.UniqueId, cancellationToken);
            var photos = detail is null
                ? ShelterLuvService.SelectPhotos(animal)
                : ShelterLuvService.SelectPhotos(detail);

            var name = detail?.Name ?? animal.Name;
            var species = detail?.Species ?? animal.Species;
            var sex = detail?.Sex ?? animal.Sex;
            var breed = detail?.Breed ?? animal.Breed;
            var weight = AnimalBioFormatter.FormatWeight(animal, detail);
            var age = AnimalBioFormatter.FormatAge(animal, detail);

            await DownloadPhotosAsync(animalDir, photos, cancellationToken);
            WriteInfoFile(animalDir, name, species, sex, weight, breed, age);

            if (isNew)
                added++;
            else
                updated++;
        }

        return new CacheSyncResult(remoteAnimals.Count, added, updated, removed);
    }

    public async Task<(CacheSyncResult Adoption, CacheSyncResult Foster)> SyncAllAsync(
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        var adoption = await SyncAsync(ViewMode.Adoption, progress, cancellationToken);
        var foster = await SyncAsync(ViewMode.Foster, progress, cancellationToken);
        return (adoption, foster);
    }

    private static bool TryParseInfoFile(string infoPath, out (string Name, string Species, string Sex, string Weight, string Breed, string Age) animal)
    {
        animal = default;
        var lines = File.ReadAllLines(infoPath);
        if (lines.Length < 2)
            return false;

        animal.Name = lines[0];
        animal.Species = lines[1];

        if (lines.Length >= 6 && IsBioFormat(lines))
        {
            animal.Sex = lines[2];
            animal.Weight = lines[3];
            animal.Breed = lines[4];
            animal.Age = lines[5];
            return true;
        }

        animal.Sex = "";
        animal.Weight = "";
        animal.Breed = "";
        animal.Age = "";
        return true;
    }

    private static bool IsBioFormat(string[] lines)
    {
        if (lines.Length < 6)
            return false;

        var sex = lines[2].Trim();
        return sex.Equals("Male", StringComparison.OrdinalIgnoreCase) ||
               sex.Equals("Female", StringComparison.OrdinalIgnoreCase) ||
               sex.Equals("Unknown", StringComparison.OrdinalIgnoreCase);
    }

    private async Task DownloadPhotosAsync(string animalDir, IReadOnlyList<ShelterPhoto> photos, CancellationToken cancellationToken)
    {
        foreach (var oldPhoto in Directory.GetFiles(animalDir, "*.jpg"))
            File.Delete(oldPhoto);

        for (var index = 0; index < photos.Count; index++)
        {
            var photo = photos[index];
            var targetPath = Path.Combine(animalDir, $"{index + 1}.jpg");
            try
            {
                var bytes = await _httpClient.GetByteArrayAsync(photo.Url, cancellationToken);
                await File.WriteAllBytesAsync(targetPath, bytes, cancellationToken);
            }
            catch
            {
                // Keep going if one photo fails.
            }
        }
    }

    private static void WriteInfoFile(
        string animalDir,
        string name,
        string species,
        string sex,
        string weight,
        string breed,
        string age)
    {
        var builder = new StringBuilder();
        builder.AppendLine(name);
        builder.AppendLine(species);
        builder.AppendLine(sex);
        builder.AppendLine(weight);
        builder.AppendLine(breed);
        builder.AppendLine(age);
        File.WriteAllText(Path.Combine(animalDir, "info.txt"), builder.ToString());
    }

    private string GetModeDirectory(ViewMode mode) =>
        Path.Combine(_cacheRoot, mode.ToString().ToLowerInvariant());

    private static string SanitizeId(string uniqueId) =>
        string.Concat(uniqueId.Where(ch => !Path.GetInvalidFileNameChars().Contains(ch)));
}

public sealed record CacheSyncResult(int Total, int Added, int Updated, int Removed);
