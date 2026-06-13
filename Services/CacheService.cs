using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
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

            var photos = GetCachedPhotoPaths(animalDir);

            if (photos.Count == 0)
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

        var remoteIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var animal in remoteAnimals)
        {
            if (CachePathHelper.TrySanitizeId(animal.UniqueId, out var sanitized))
                remoteIds.Add(sanitized);
        }

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
        var skipped = 0;

        foreach (var animal in remoteAnimals)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (!CachePathHelper.TrySanitizeId(animal.UniqueId, out var id))
            {
                LogService.Error($"Skipping animal with invalid ID: {animal.UniqueId}");
                skipped++;
                continue;
            }

            var animalDir = CachePathHelper.ResolveAnimalDirectory(_cacheRoot, mode, id);
            if (animalDir is null)
            {
                LogService.Error($"Skipping animal with unsafe cache path for ID: {id}");
                skipped++;
                continue;
            }

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
            var infoContent = BuildInfoFileContent(name, species, sex, weight, breed, age);

            var photosChanged = PhotosAreCurrent(animalDir, photos)
                ? false
                : await DownloadPhotosAsync(animalDir, photos, cancellationToken);

            if (isNew && !photosChanged)
            {
                skipped++;
                TryDeleteEmptyAnimalDir(animalDir);
                continue;
            }

            if (!photosChanged && !InfoFileChanged(animalDir, infoContent))
                continue;

            await AtomicFileHelper.WriteAllTextAsync(Path.Combine(animalDir, "info.txt"), infoContent, cancellationToken);

            if (isNew)
                added++;
            else
                updated++;
        }

        return new CacheSyncResult(remoteAnimals.Count, added, updated, removed, skipped);
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

    private async Task<bool> DownloadPhotosAsync(
        string animalDir,
        IReadOnlyList<ShelterPhoto> photos,
        CancellationToken cancellationToken)
    {
        var tempPaths = new List<(string Path, string Extension)>();

        try
        {
            for (var index = 0; index < photos.Count; index++)
            {
                var photo = photos[index];
                if (!PhotoUrlValidator.IsAllowed(photo.Url))
                {
                    LogService.Error($"Rejected photo URL for download: {photo.Url}");
                    continue;
                }

                var tempPath = Path.Combine(animalDir, $"{index + 1}.tmp.downloading");
                try
                {
                    var bytes = await _httpClient.GetByteArrayAsync(photo.Url, cancellationToken);
                    if (bytes.Length == 0 || bytes.Length > PhotoUrlValidator.MaxBytes)
                    {
                        LogService.Error($"Rejected photo size ({bytes.Length} bytes) from {photo.Url}");
                        continue;
                    }

                    if (!PhotoUrlValidator.TryGetImageExtension(bytes, out var extension))
                    {
                        LogService.Error($"Rejected unsupported image content from {photo.Url}");
                        continue;
                    }

                    tempPaths.Add((tempPath, extension));
                    await AtomicFileHelper.WriteAllBytesAsync(tempPath, bytes, cancellationToken);
                }
                catch (Exception ex)
                {
                    LogService.Error($"Failed downloading photo from {photo.Url}", ex);
                    TryDeleteFile(tempPath);
                }
            }

            if (tempPaths.Count == 0)
            {
                if (GetCachedPhotoPaths(animalDir).Count > 0)
                    return false;

                LogService.Error($"No photos downloaded and none cached in {animalDir}");
                return false;
            }

            DeleteCachedPhotos(animalDir);

            for (var index = 0; index < tempPaths.Count; index++)
            {
                var (tempPath, extension) = tempPaths[index];
                var finalPath = Path.Combine(animalDir, $"{index + 1}.{extension}");
                File.Move(tempPath, finalPath, overwrite: true);
                tempPaths[index] = ("", extension);
            }

            await SavePhotoManifestAsync(animalDir, photos, cancellationToken);
            return true;
        }
        finally
        {
            foreach (var (tempPath, _) in tempPaths)
            {
                if (!string.IsNullOrWhiteSpace(tempPath))
                    TryDeleteFile(tempPath);
            }
        }
    }

    private static bool InfoFileChanged(string animalDir, string newContent)
    {
        var infoPath = Path.Combine(animalDir, "info.txt");
        if (!File.Exists(infoPath))
            return true;

        var existing = File.ReadAllText(infoPath);
        return !string.Equals(existing, newContent, StringComparison.Ordinal);
    }

    private static string BuildInfoFileContent(
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
        return builder.ToString();
    }

    private static void TryDeleteEmptyAnimalDir(string animalDir)
    {
        try
        {
            if (!Directory.Exists(animalDir))
                return;

            if (Directory.GetFiles(animalDir).Length == 0 &&
                Directory.GetDirectories(animalDir).Length == 0)
            {
                Directory.Delete(animalDir, recursive: true);
            }
        }
        catch (Exception ex)
        {
            LogService.Error($"Failed cleaning empty cache directory {animalDir}", ex);
        }
    }

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
                File.Delete(path);
        }
        catch (Exception ex)
        {
            LogService.Error($"Failed deleting temp file {path}", ex);
        }
    }

    private static bool PhotosAreCurrent(string animalDir, IReadOnlyList<ShelterPhoto> photos)
    {
        if (photos.Count == 0)
            return false;

        var manifestPath = Path.Combine(animalDir, "photos.json");
        if (!File.Exists(manifestPath))
            return false;

        try
        {
            var manifest = JsonSerializer.Deserialize<List<PhotoManifestEntry>>(File.ReadAllText(manifestPath));
            if (manifest is null || manifest.Count != photos.Count)
                return false;

            for (var index = 0; index < photos.Count; index++)
            {
                if (!string.Equals(manifest[index].Url, photos[index].Url, StringComparison.Ordinal))
                    return false;

                if (!PhotoFileExists(animalDir, index))
                    return false;
            }

            return true;
        }
        catch (Exception ex)
        {
            LogService.Error($"Failed reading photo manifest in {animalDir}", ex);
            return false;
        }
    }

    private static async Task SavePhotoManifestAsync(
        string animalDir,
        IReadOnlyList<ShelterPhoto> photos,
        CancellationToken cancellationToken)
    {
        var entries = photos.Select(photo => new PhotoManifestEntry(photo.Url)).ToList();
        var json = JsonSerializer.Serialize(entries);
        await AtomicFileHelper.WriteAllTextAsync(Path.Combine(animalDir, "photos.json"), json, cancellationToken);
    }

    private sealed record PhotoManifestEntry(string Url);

    private static List<string> GetCachedPhotoPaths(string animalDir) =>
        Directory.GetFiles(animalDir)
            .Where(IsCachedPhotoFile)
            .OrderBy(GetCachedPhotoOrder)
            .ToList();

    private static bool IsCachedPhotoFile(string path)
    {
        var name = Path.GetFileName(path);
        if (name.Contains(".downloading", StringComparison.OrdinalIgnoreCase))
            return false;

        return name.EndsWith(".jpg", StringComparison.OrdinalIgnoreCase) ||
               name.EndsWith(".png", StringComparison.OrdinalIgnoreCase);
    }

    private static int GetCachedPhotoOrder(string path)
    {
        var name = Path.GetFileNameWithoutExtension(path);
        return int.TryParse(name, out var order) ? order : int.MaxValue;
    }

    private static bool PhotoFileExists(string animalDir, int index) =>
        File.Exists(Path.Combine(animalDir, $"{index + 1}.jpg")) ||
        File.Exists(Path.Combine(animalDir, $"{index + 1}.png"));

    private static void DeleteCachedPhotos(string animalDir)
    {
        foreach (var file in Directory.GetFiles(animalDir).Where(IsCachedPhotoFile))
            File.Delete(file);
    }

    private string GetModeDirectory(ViewMode mode) =>
        Path.Combine(_cacheRoot, mode.ToString().ToLowerInvariant());
}

public sealed record CacheSyncResult(int Total, int Added, int Updated, int Removed, int Skipped = 0);
