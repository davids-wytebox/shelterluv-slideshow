using ShelterPetViewer.Models;

namespace ShelterPetViewer.Services;

public static class AnimalBioFormatter
{
    public static string FormatWeight(ShelterAnimalSummary summary, ShelterAnimalDetail? detail)
    {
        if (detail?.Weight is > 0)
        {
            var units = string.IsNullOrWhiteSpace(detail.WeightUnits) ? "lb" : detail.WeightUnits;
            var value = detail.Weight % 1 == 0
                ? ((int)detail.Weight.Value).ToString()
                : detail.Weight.Value.ToString("0.#");
            return $"{value} {units}";
        }

        if (!string.IsNullOrWhiteSpace(detail?.WeightGroup))
            return detail.WeightGroup;

        if (!string.IsNullOrWhiteSpace(summary.WeightGroup))
            return summary.WeightGroup;

        return "";
    }

    public static string FormatAge(ShelterAnimalSummary summary, ShelterAnimalDetail? detail)
    {
        var fromBirthday = FormatAgeFromBirthday(detail?.Birthday);
        if (!string.IsNullOrWhiteSpace(fromBirthday))
            return fromBirthday;

        var ageGroup = detail?.AgeGroup ?? summary.AgeGroup;
        if (ageGroup is null)
            return "";

        return FormatAgeGroup(ageGroup);
    }

    public static string FormatCardText(CachedAnimal animal)
    {
        var lines = new List<string>();

        if (!string.IsNullOrWhiteSpace(animal.Sex))
            lines.Add(animal.Sex);
        if (!string.IsNullOrWhiteSpace(animal.Age))
            lines.Add(animal.Age);
        if (!string.IsNullOrWhiteSpace(animal.Weight))
            lines.Add(NormalizeWeightDisplay(animal.Weight));

        return string.Join(Environment.NewLine, lines);
    }

    private static string FormatAgeFromBirthday(string? birthday)
    {
        if (string.IsNullOrWhiteSpace(birthday) || !long.TryParse(birthday, out var unixSeconds))
            return "";

        var birthDate = DateTimeOffset.FromUnixTimeSeconds(unixSeconds).Date;
        var today = DateTime.Today;
        if (birthDate > today)
            return "";

        var years = today.Year - birthDate.Year;
        var months = today.Month - birthDate.Month;
        if (today.Day < birthDate.Day)
            months--;
        if (months < 0)
        {
            years--;
            months += 12;
        }

        if (years >= 2)
            return $"{years} years";
        if (years == 1)
            return "1 year";
        if (months >= 2)
            return $"{months} months";
        if (months == 1)
            return "1 month";

        var days = (today - birthDate).Days;
        if (days >= 14)
        {
            var weeks = days / 7;
            return weeks == 1 ? "1 week" : $"{weeks} weeks";
        }

        return days <= 1 ? "1 day" : $"{days} days";
    }

    private static string FormatAgeGroup(ShelterAgeGroup ageGroup)
    {
        if (!string.IsNullOrWhiteSpace(ageGroup.Duration))
        {
            var duration = ageGroup.Duration.Trim().Trim('(', ')');
            if (!string.IsNullOrWhiteSpace(ageGroup.Name))
                return $"{ageGroup.Name} {duration}";
        }

        if (!string.IsNullOrWhiteSpace(ageGroup.NameWithDuration))
            return ageGroup.NameWithDuration.Replace(" (", " ").TrimEnd(')');

        return ageGroup.Name;
    }

    private static string NormalizeWeightDisplay(string weight)
    {
        return weight.EndsWith(" lbs", StringComparison.OrdinalIgnoreCase)
            ? weight[..^1]
            : weight;
    }
}
