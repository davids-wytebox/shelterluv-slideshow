using System.Net.Http;
using System.Text.Json;
using ShelterPetViewer.Models;
using ShelterPetViewer.Serialization;

var client = new HttpClient();
client.DefaultRequestHeaders.UserAgent.ParseAdd("ShelterPetViewer-test/1.0");
var options = new JsonSerializerOptions
{
    PropertyNameCaseInsensitive = true
};

foreach (var query in new[] { "?animalType=Dog", "?animalType=Cat" })
{
    var url = $"https://new.shelterluv.com/api/v3/available-animals/38131{query}";
    Console.WriteLine($"Fetching {url}");
    var json = await client.GetStringAsync(url);
    Console.WriteLine($"  bytes={json.Length}");
    var payload = JsonSerializer.Deserialize<ShelterAnimalListResponse>(json, options);
    Console.WriteLine($"  animals={payload?.Animals.Count}");
}

Console.WriteLine("OK");
