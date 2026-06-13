using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Windows;
using System.Windows.Forms;
using Application = System.Windows.Application;
using ShelterPetViewer.Models;
using ShelterPetViewer.Services;

namespace ShelterPetViewer;

public partial class App : Application
{
    private static readonly int[] AutoAdvanceOptions = [10, 15, 20, 30, 45, 60];

    private NotifyIcon? _trayIcon;
    private readonly List<FullscreenWindow> _fullscreenWindows = new();
    private SlideshowSession? _slideshowSession;
    private AppSettings _settings = new();
    private SettingsService _settingsService = new();
    private CacheService _cacheService = null!;
    private HttpClient _httpClient = null!;
    private bool _isSyncing;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            LogService.Error("Unhandled exception", args.ExceptionObject as Exception);

        DispatcherUnhandledException += (_, args) =>
        {
            LogService.Error("UI thread exception", args.Exception);
            args.Handled = true;
        };

        _settings = _settingsService.Load();
        NormalizeSettings();
        if (_settings.StartWithWindows && !StartupService.IsEnabled())
            StartupService.SetEnabled(true);

        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromMinutes(5)
        };
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("ShelterPetViewer/1.0");

        var shelterService = new ShelterLuvService(_httpClient);
        _cacheService = new CacheService(shelterService, _httpClient);

        CreateTrayIcon();

        if (_cacheService.LoadCachedAnimals(ViewMode.Adoption).Count == 0 &&
            _cacheService.LoadCachedAnimals(ViewMode.Foster).Count == 0)
        {
            _trayIcon!.ShowBalloonTip(
                5000,
                "Shelter Pet Viewer",
                "No cached animals yet. Right-click the tray icon and choose Update Cache while online.",
                ToolTipIcon.Info);
        }
    }

    private void CreateTrayIcon()
    {
        _trayIcon = new NotifyIcon
        {
            Icon = CreateTrayIconImage(),
            Visible = true,
            Text = "Shelter Pet Viewer"
        };

        RefreshTrayMenu();

        _trayIcon.DoubleClick += (_, _) => ShowFullscreen();
    }

    private void RefreshTrayMenu()
    {
        if (_trayIcon is null)
            return;

        var menu = new ContextMenuStrip();

        var showItem = new ToolStripMenuItem("Show Fullscreen", null, (_, _) => ShowFullscreen());
        var updateItem = new ToolStripMenuItem("Update Cache", null, (_, _) => _ = UpdateCacheAsync());
        menu.Items.Add(showItem);
        menu.Items.Add(updateItem);
        menu.Items.Add(new ToolStripSeparator());

        var modeMenu = new ToolStripMenuItem("Animal Set");
        var adoptionItem = new ToolStripMenuItem("Adoption (Dogs + Cats)")
        {
            Checked = _settings.Mode == ViewMode.Adoption,
            CheckOnClick = true
        };
        var fosterItem = new ToolStripMenuItem("Foster (Dogs + Cats)")
        {
            Checked = _settings.Mode == ViewMode.Foster,
            CheckOnClick = true
        };

        adoptionItem.Click += (_, _) => SetMode(ViewMode.Adoption, adoptionItem, fosterItem);
        fosterItem.Click += (_, _) => SetMode(ViewMode.Foster, adoptionItem, fosterItem);

        modeMenu.DropDownItems.Add(adoptionItem);
        modeMenu.DropDownItems.Add(fosterItem);
        menu.Items.Add(modeMenu);

        var displayMenu = new ToolStripMenuItem("Display On");
        var secondaryItem = new ToolStripMenuItem("Secondary screen (work on primary)")
        {
            Checked = _settings.DisplayTarget == DisplayTarget.SecondaryScreen,
            CheckOnClick = true
        };
        var primaryItem = new ToolStripMenuItem("Primary screen only")
        {
            Checked = _settings.DisplayTarget == DisplayTarget.PrimaryScreen,
            CheckOnClick = true
        };
        var allScreensItem = new ToolStripMenuItem("All screens")
        {
            Checked = _settings.DisplayTarget == DisplayTarget.AllScreens,
            CheckOnClick = true
        };

        secondaryItem.Click += (_, _) => SetDisplayTarget(DisplayTarget.SecondaryScreen, secondaryItem, primaryItem, allScreensItem);
        primaryItem.Click += (_, _) => SetDisplayTarget(DisplayTarget.PrimaryScreen, secondaryItem, primaryItem, allScreensItem);
        allScreensItem.Click += (_, _) => SetDisplayTarget(DisplayTarget.AllScreens, secondaryItem, primaryItem, allScreensItem);

        displayMenu.DropDownItems.Add(secondaryItem);
        displayMenu.DropDownItems.Add(primaryItem);
        displayMenu.DropDownItems.Add(allScreensItem);
        menu.Items.Add(displayMenu);

        var intervalMenu = new ToolStripMenuItem("Slide Interval");
        foreach (var seconds in AutoAdvanceOptions)
        {
            var intervalItem = new ToolStripMenuItem($"{seconds} seconds")
            {
                Checked = _settings.AutoAdvanceSeconds == seconds,
                CheckOnClick = true
            };
            var selectedSeconds = seconds;
            intervalItem.Click += (_, _) => SetAutoAdvanceSeconds(selectedSeconds, intervalMenu);
            intervalMenu.DropDownItems.Add(intervalItem);
        }
        menu.Items.Add(intervalMenu);

        var startupItem = new ToolStripMenuItem("Start with Windows")
        {
            Checked = StartupService.IsEnabled(),
            CheckOnClick = true
        };
        startupItem.Click += (_, _) =>
        {
            var enabled = startupItem.Checked;
            StartupService.SetEnabled(enabled);
            _settings.StartWithWindows = enabled;
            _settingsService.Save(_settings);
        };
        menu.Items.Add(startupItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("Open Log File", null, (_, _) => OpenLogFile()));
        menu.Items.Add(new ToolStripSeparator());

        menu.Items.Add(new ToolStripMenuItem("Exit", null, (_, _) => ExitApp()));

        _trayIcon.ContextMenuStrip = menu;
    }

    private void SetMode(ViewMode mode, ToolStripMenuItem adoptionItem, ToolStripMenuItem fosterItem)
    {
        _settings.Mode = mode;
        adoptionItem.Checked = mode == ViewMode.Adoption;
        fosterItem.Checked = mode == ViewMode.Foster;
        _settingsService.Save(_settings);

        if (_fullscreenWindows.Count > 0)
        {
            CloseAllFullscreen();
            ShowFullscreen();
        }
    }

    private void SetAutoAdvanceSeconds(int seconds, ToolStripMenuItem intervalMenu)
    {
        _settings.AutoAdvanceSeconds = seconds;
        _settingsService.Save(_settings);

        foreach (ToolStripMenuItem item in intervalMenu.DropDownItems)
            item.Checked = item.Text == $"{seconds} seconds";

        _slideshowSession?.SetAutoAdvanceSeconds(seconds);
        LogService.Info($"Slide interval set to {seconds} seconds.");
    }

    private void NormalizeSettings()
    {
        if (!AutoAdvanceOptions.Contains(_settings.AutoAdvanceSeconds))
            _settings.AutoAdvanceSeconds = 45;
    }

    private void SetDisplayTarget(
        DisplayTarget target,
        ToolStripMenuItem secondaryItem,
        ToolStripMenuItem primaryItem,
        ToolStripMenuItem allScreensItem)
    {
        _settings.DisplayTarget = target;
        secondaryItem.Checked = target == DisplayTarget.SecondaryScreen;
        primaryItem.Checked = target == DisplayTarget.PrimaryScreen;
        allScreensItem.Checked = target == DisplayTarget.AllScreens;
        _settingsService.Save(_settings);

        if (_fullscreenWindows.Count > 0)
        {
            CloseAllFullscreen();
            ShowFullscreen();
        }
    }

    private void ShowFullscreen()
    {
        if (_fullscreenWindows.Count > 0)
        {
            _fullscreenWindows[0].Activate();
            return;
        }

        var animals = _cacheService.LoadCachedAnimals(_settings.Mode);
        var screens = DisplayService.GetScreens(_settings.DisplayTarget);
        if (screens.Count == 0)
        {
            _trayIcon?.ShowBalloonTip(4000, "No Display", "No screens were detected.", ToolTipIcon.Warning);
            return;
        }

        _slideshowSession = new SlideshowSession(animals, _settings.AutoAdvanceSeconds, _settings.HistorySize);

        foreach (var screen in screens)
        {
            var bounds = DisplayService.GetBounds(screen);
            LogService.Info(
                $"Opening fullscreen on {screen.DeviceName} (primary={screen.Primary}, " +
                $"pixels={screen.Bounds}, wpf={bounds}).");

            var window = new FullscreenWindow(_slideshowSession, bounds);
            window.CloseRequested += CloseAllFullscreen;
            window.Closed += OnFullscreenWindowClosed;
            _fullscreenWindows.Add(window);
            window.Show();
        }

        _slideshowSession.Start();
        LogService.Info($"Started fullscreen on {screens.Count} screen(s) using {_settings.DisplayTarget}.");
    }

    private void OnFullscreenWindowClosed(object? sender, EventArgs e)
    {
        if (sender is not FullscreenWindow window)
            return;

        window.CloseRequested -= CloseAllFullscreen;
        window.Closed -= OnFullscreenWindowClosed;
        _fullscreenWindows.Remove(window);

        if (_fullscreenWindows.Count == 0)
        {
            _slideshowSession?.Dispose();
            _slideshowSession = null;
        }
    }

    private void CloseAllFullscreen()
    {
        if (_fullscreenWindows.Count == 0)
            return;

        _slideshowSession?.Stop();
        var windows = _fullscreenWindows.ToList();
        _fullscreenWindows.Clear();

        foreach (var window in windows)
        {
            window.CloseRequested -= CloseAllFullscreen;
            window.Closed -= OnFullscreenWindowClosed;
            window.Close();
        }

        _slideshowSession?.Dispose();
        _slideshowSession = null;
    }

    private async Task UpdateCacheAsync()
    {
        if (_isSyncing)
            return;

        _isSyncing = true;
        try
        {
            LogService.Info("Starting cache update for adoption and foster.");
            _trayIcon!.Text = "Updating cache...";
            var (adoption, foster) = await _cacheService.SyncAllAsync(new Progress<string>(UpdateTrayText));
            var added = adoption.Added + foster.Added;
            var updated = adoption.Updated + foster.Updated;
            var removed = adoption.Removed + foster.Removed;
            var total = adoption.Total + foster.Total;
            LogService.Info(
                $"Cache update finished: {total} total " +
                $"(adoption {adoption.Total}, foster {foster.Total}), " +
                $"{added} added, {updated} updated, {removed} removed.");
            _trayIcon.ShowBalloonTip(
                4000,
                "Cache Updated",
                $"{total} animals cached ({adoption.Total} adoption, {foster.Total} foster). " +
                $"{added} new, {updated} updated, {removed} removed.",
                ToolTipIcon.Info);
        }
        catch (Exception ex)
        {
            LogService.Error("Cache update failed", ex);
            _trayIcon!.ShowBalloonTip(
                5000,
                "Update Failed",
                $"{ex.Message} See log: {LogService.LogFilePath}",
                ToolTipIcon.Error);
        }
        finally
        {
            _isSyncing = false;
            _trayIcon!.Text = "Shelter Pet Viewer";
        }
    }

    private static void OpenLogFile()
    {
        if (!File.Exists(LogService.LogFilePath))
            LogService.Info("Log file created.");

        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
        {
            FileName = LogService.LogFilePath,
            UseShellExecute = true
        });
    }

    private void UpdateTrayText(string text)
    {
        if (_trayIcon is null)
            return;

        var trayText = text.Length > 63 ? text[..63] : text;
        if (Dispatcher.CheckAccess())
            _trayIcon.Text = trayText;
        else
            Dispatcher.BeginInvoke(() => _trayIcon.Text = trayText);
    }

    private void ExitApp()
    {
        CloseAllFullscreen();

        if (_trayIcon is not null)
        {
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }

        _httpClient.Dispose();
        Shutdown();
    }

    private static Icon CreateTrayIconImage()
    {
        using var bitmap = new Bitmap(32, 32);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.Clear(Color.FromArgb(255, 74, 111, 165));
        using var brush = new SolidBrush(Color.White);
        graphics.FillEllipse(brush, 8, 8, 16, 16);
        graphics.FillEllipse(brush, 4, 4, 7, 7);
        graphics.FillEllipse(brush, 21, 4, 7, 7);
        return Icon.FromHandle(bitmap.GetHicon());
    }
}
