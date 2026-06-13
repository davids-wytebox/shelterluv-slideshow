using System.Text.Json;
using System.Text.Json.Serialization;
using ShelterPetViewer.Models;

namespace ShelterPetViewer.Serialization;

public sealed class ShelterPhotosConverter : JsonConverter<List<ShelterPhoto>>
{
    private static readonly JsonSerializerOptions PhotoOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public override List<ShelterPhoto> Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        switch (reader.TokenType)
        {
            case JsonTokenType.Null:
                return [];
            case JsonTokenType.StartArray:
                return JsonSerializer.Deserialize<List<ShelterPhoto>>(ref reader, PhotoOptions) ?? [];
            case JsonTokenType.StartObject:
            {
                var dictionary = JsonSerializer.Deserialize<Dictionary<string, ShelterPhoto>>(ref reader, PhotoOptions);
                return dictionary?.Values.ToList() ?? [];
            }
            default:
                throw new JsonException($"Unexpected JSON token for photos: {reader.TokenType}");
        }
    }

    public override void Write(Utf8JsonWriter writer, List<ShelterPhoto> value, JsonSerializerOptions options) =>
        JsonSerializer.Serialize(writer, value, PhotoOptions);
}
