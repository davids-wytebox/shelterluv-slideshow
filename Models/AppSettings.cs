namespace ShelterPetViewer.Models;

public enum ViewMode
{
    Adoption,
    Foster
}

public enum DisplayTarget
{
    SecondaryScreen,
    PrimaryScreen,
    AllScreens
}

public sealed class AppSettings
{
    public ViewMode Mode { get; set; } = ViewMode.Adoption;
    public DisplayTarget DisplayTarget { get; set; } = DisplayTarget.SecondaryScreen;
    public int AutoAdvanceSeconds { get; set; } = 45;
    public int HistorySize { get; set; } = 20;
    public bool StartWithWindows { get; set; } = true;
}
