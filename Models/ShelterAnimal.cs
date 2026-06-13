using System.Text.Json.Serialization;
using ShelterPetViewer.Serialization;

namespace ShelterPetViewer.Models;

public sealed class ShelterAnimalListResponse
{
    [JsonPropertyName("animals")]
    public List<ShelterAnimalSummary> Animals { get; set; } = [];
}

public sealed class ShelterAnimalSummary
{
    [JsonPropertyName("nid")]
    public long Nid { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("uniqueId")]
    public string UniqueId { get; set; } = "";

    [JsonPropertyName("species")]
    public string Species { get; set; } = "";

    [JsonPropertyName("breed")]
    public string Breed { get; set; } = "";

    [JsonPropertyName("sex")]
    public string Sex { get; set; } = "";

    [JsonPropertyName("weight_group")]
    public string WeightGroup { get; set; } = "";

    [JsonPropertyName("age_group")]
    public ShelterAgeGroup? AgeGroup { get; set; }

    [JsonPropertyName("attributes")]
    public List<string> Attributes { get; set; } = [];

    [JsonPropertyName("photos")]
    [JsonConverter(typeof(ShelterPhotosConverter))]
    public List<ShelterPhoto> Photos { get; set; } = [];

    [JsonPropertyName("public_url")]
    public string PublicUrl { get; set; } = "";
}

public sealed class ShelterAgeGroup
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("name_with_duration")]
    public string NameWithDuration { get; set; } = "";

    [JsonPropertyName("duration")]
    public string Duration { get; set; } = "";
}

public sealed class ShelterPhoto
{
    [JsonPropertyName("id")]
    public long Id { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("url")]
    public string Url { get; set; } = "";

    [JsonPropertyName("isCover")]
    public bool IsCover { get; set; }

    [JsonPropertyName("order_column")]
    public int OrderColumn { get; set; }
}

public sealed class ShelterAnimalDetail
{
    [JsonPropertyName("uniqueId")]
    public string UniqueId { get; set; } = "";

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("species")]
    public string Species { get; set; } = "";

    [JsonPropertyName("breed")]
    public string Breed { get; set; } = "";

    [JsonPropertyName("sex")]
    public string Sex { get; set; } = "";

    [JsonPropertyName("weight")]
    public double? Weight { get; set; }

    [JsonPropertyName("weight_units")]
    public string WeightUnits { get; set; } = "";

    [JsonPropertyName("weight_group")]
    public string WeightGroup { get; set; } = "";

    [JsonPropertyName("birthday")]
    public string Birthday { get; set; } = "";

    [JsonPropertyName("age_group")]
    public ShelterAgeGroup? AgeGroup { get; set; }

    [JsonPropertyName("attributes")]
    public List<string> Attributes { get; set; } = [];

    [JsonPropertyName("photos")]
    [JsonConverter(typeof(ShelterPhotosConverter))]
    public List<ShelterPhoto> Photos { get; set; } = [];

    [JsonPropertyName("kennel_description")]
    public string? KennelDescription { get; set; }
}
