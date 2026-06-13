namespace ShelterPetViewer.Models;

public sealed class CachedAnimal
{
    public required string Id { get; init; }
    public required string Name { get; init; }
    public required string Species { get; init; }
    public string Sex { get; init; } = "";
    public string Weight { get; init; } = "";
    public string Breed { get; init; } = "";
    public string Age { get; init; } = "";
    public required IReadOnlyList<string> PhotoPaths { get; init; }
}
