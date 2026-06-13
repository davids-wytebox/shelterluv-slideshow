using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Forms;
using ShelterPetViewer.Models;

namespace ShelterPetViewer.Services;

public static class DisplayService
{
    private const uint MonitorDefaultToNearest = 2;

    public static IReadOnlyList<Screen> GetScreens(DisplayTarget target)
    {
        var screens = Screen.AllScreens;
        if (screens.Length == 0)
            return [];

        return target switch
        {
            DisplayTarget.PrimaryScreen => [Screen.PrimaryScreen ?? screens[0]],
            DisplayTarget.SecondaryScreen => [GetSecondaryScreen(screens)],
            DisplayTarget.AllScreens => screens,
            _ => [Screen.PrimaryScreen ?? screens[0]]
        };
    }

    public static bool HasSecondaryScreen() =>
        Screen.AllScreens.Any(screen => !screen.Primary);

    public static string DescribeTarget(DisplayTarget target)
    {
        return target switch
        {
            DisplayTarget.SecondaryScreen when HasSecondaryScreen() =>
                "Secondary screen (use primary for paperwork)",
            DisplayTarget.SecondaryScreen =>
                "Secondary screen (only one monitor detected, using primary)",
            DisplayTarget.PrimaryScreen => "Primary screen only",
            DisplayTarget.AllScreens => "All screens",
            _ => "Primary screen only"
        };
    }

    public static Rect GetBounds(Screen screen)
    {
        var bounds = screen.Bounds;
        var (dpiX, dpiY) = GetDpiForScreen(screen);

        return new Rect(
            bounds.X * 96.0 / dpiX,
            bounds.Y * 96.0 / dpiY,
            bounds.Width * 96.0 / dpiX,
            bounds.Height * 96.0 / dpiY);
    }

    private static (double dpiX, double dpiY) GetDpiForScreen(Screen screen)
    {
        try
        {
            var bounds = screen.Bounds;
            var point = new POINT
            {
                x = bounds.Left + bounds.Width / 2,
                y = bounds.Top + bounds.Height / 2
            };

            var monitor = MonitorFromPoint(point, MonitorDefaultToNearest);
            if (monitor != IntPtr.Zero &&
                GetDpiForMonitor(monitor, MonitorDpiType.Effective, out var dpiX, out var dpiY) == 0)
            {
                return (dpiX, dpiY);
            }
        }
        catch
        {
            // Fall back to the primary monitor DPI below.
        }

        using var graphics = Graphics.FromHwnd(IntPtr.Zero);
        return (graphics.DpiX, graphics.DpiY);
    }

    private static Screen GetSecondaryScreen(Screen[] screens)
    {
        foreach (var screen in screens)
        {
            if (!screen.Primary)
                return screen;
        }

        return Screen.PrimaryScreen ?? screens[0];
    }

    private enum MonitorDpiType
    {
        Effective = 0
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int x;
        public int y;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromPoint(POINT pt, uint dwFlags);

    [DllImport("shcore.dll")]
    private static extern int GetDpiForMonitor(
        IntPtr hmonitor,
        MonitorDpiType dpiType,
        out uint dpiX,
        out uint dpiY);
}
