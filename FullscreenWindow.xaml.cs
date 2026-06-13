using System.Collections.Concurrent;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using ShelterPetViewer.Models;
using ShelterPetViewer.Services;
using WpfPoint = System.Windows.Point;

namespace ShelterPetViewer;

public partial class FullscreenWindow : Window
{
    private static readonly ConcurrentDictionary<string, (long WriteTimeUtcTicks, BitmapImage Image)> BitmapCache = new();

    private readonly SlideshowSession _session;
    private readonly Rect _screenBounds;
    private CachedAnimal? _currentAnimal;
    private IReadOnlyList<BitmapImage>? _currentPhotos;
    private int _renderGeneration;

    public event Action? CloseRequested;

    private sealed record PhotoPlacement(double CenterX, double CenterY, double Scale, double Rotation, int ZIndex);

    public FullscreenWindow(SlideshowSession session, Rect screenBounds)
    {
        InitializeComponent();
        _session = session;
        _screenBounds = screenBounds;
        _session.AnimalChanged += OnAnimalChanged;
        ApplyScreenBounds();
    }

    private void ApplyScreenBounds()
    {
        WindowStartupLocation = WindowStartupLocation.Manual;
        WindowState = WindowState.Normal;
        Left = _screenBounds.Left;
        Top = _screenBounds.Top;
        Width = _screenBounds.Width;
        Height = _screenBounds.Height;
    }

    private void PhotoCanvas_SizeChanged(object sender, SizeChangedEventArgs e)
    {
        if (_currentPhotos is null || _currentPhotos.Count == 0 || _currentAnimal is null)
            return;

        if (e.NewSize.Width <= 0 || e.NewSize.Height <= 0)
            return;

        LayoutPhotos(_currentPhotos, _currentAnimal);
    }

    private void Window_Loaded(object sender, RoutedEventArgs e)
    {
        ApplyScreenBounds();
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _session.AnimalChanged -= OnAnimalChanged;
    }

    public void HandleSlideshowKey(Key key)
    {
        switch (key)
        {
            case Key.Escape:
                CloseRequested?.Invoke();
                break;
            case Key.Left:
                _session.ShowPrevious();
                _session.ResetAutoTimer();
                break;
            case Key.Right:
                _session.ShowNext();
                _session.ResetAutoTimer();
                break;
        }
    }

    private void Window_KeyDown(object sender, System.Windows.Input.KeyEventArgs e) => HandleSlideshowKey(e.Key);

    private void OnAnimalChanged(CachedAnimal? animal)
    {
        if (animal is null)
        {
            Interlocked.Increment(ref _renderGeneration);
            SetDisplayName("No cached animals");
            BioText.Text = "Use the tray icon to update the cache while online.";
            BioCard.Visibility = Visibility.Visible;
            QrCodeCard.Visibility = Visibility.Collapsed;
            PhotoCanvas.Children.Clear();
            _currentAnimal = null;
            _currentPhotos = null;
            return;
        }

        _ = RenderAnimalAsync(animal);
    }

    private async Task RenderAnimalAsync(CachedAnimal animal)
    {
        var generation = Interlocked.Increment(ref _renderGeneration);
        UpdateAnimalChrome(animal);

        var paths = animal.PhotoPaths
            .Where(File.Exists)
            .Take(5)
            .ToList();

        var qrTask = UpdateQrCodeAsync(animal.Id, generation);
        var photos = await Task.Run(() =>
            paths
                .Select(LoadBitmapCached)
                .Where(image => image is not null)
                .Cast<BitmapImage>()
                .ToList());

        await qrTask;

        if (generation != Volatile.Read(ref _renderGeneration))
            return;

        _currentAnimal = animal;
        _currentPhotos = photos;
        PhotoCanvas.Children.Clear();

        if (photos.Count == 0)
            return;

        LayoutPhotos(photos, animal);
    }

    private void UpdateAnimalChrome(CachedAnimal animal)
    {
        var (displayName, _, _) = AnimalNameFormatter.Parse(animal.Name);
        SetDisplayName(displayName);
        var bioText = AnimalBioFormatter.FormatCardText(animal);
        BioText.Text = bioText;
        BioCard.Visibility = string.IsNullOrWhiteSpace(bioText)
            ? Visibility.Collapsed
            : Visibility.Visible;
    }

    private async Task UpdateQrCodeAsync(string uniqueId, int generation)
    {
        var url = QrCodeService.GetAnimalUrl(uniqueId);
        var qrCode = await Task.Run(() => QrCodeService.CreateQrCode(url));

        if (generation != Volatile.Read(ref _renderGeneration))
            return;

        QrCodeImage.Source = qrCode;
        QrCodeCard.Visibility = Visibility.Visible;
    }

    private void LayoutPhotos(IReadOnlyList<BitmapImage> photos, CachedAnimal animal)
    {
        PhotoCanvas.Children.Clear();

        var layoutRandom = new Random(animal.Id.GetHashCode(StringComparison.OrdinalIgnoreCase));
        if (photos.Count == 1)
            LayoutSinglePhoto(photos[0]);
        else
            LayoutMultiplePhotos(photos, layoutRandom);
    }

    private void LayoutSinglePhoto(BitmapImage photo)
    {
        var canvasWidth = PhotoCanvas.ActualWidth > 0 ? PhotoCanvas.ActualWidth : ActualWidth;
        var canvasHeight = PhotoCanvas.ActualHeight > 0 ? PhotoCanvas.ActualHeight : ActualHeight;
        var baseSize = Math.Min(canvasWidth, canvasHeight);

        PlacePhoto(photo, canvasWidth, canvasHeight, new PhotoPlacement(0.50, 0.52, 0.78, -2, 1), baseSize, new Random(0));
    }

    private void LayoutMultiplePhotos(IReadOnlyList<BitmapImage> photos, Random layoutRandom)
    {
        var canvasWidth = PhotoCanvas.ActualWidth > 0 ? PhotoCanvas.ActualWidth : ActualWidth;
        var canvasHeight = PhotoCanvas.ActualHeight > 0 ? PhotoCanvas.ActualHeight : ActualHeight;
        var baseSize = Math.Min(canvasWidth, canvasHeight);
        var placements = BuildPlacements(photos.Count);

        for (var i = 0; i < photos.Count; i++)
        {
            var placementIndex = GetPlacementIndex(photos.Count, i);
            PlacePhoto(photos[i], canvasWidth, canvasHeight, placements[placementIndex], baseSize, layoutRandom);
        }
    }

    private void PlacePhoto(
        BitmapImage photo,
        double canvasWidth,
        double canvasHeight,
        PhotoPlacement placement,
        double baseSize,
        Random layoutRandom)
    {
        var maxSide = baseSize * placement.Scale;
        var frame = CreatePhotoFrame(photo, maxSide, maxSide);
        var rotation = placement.Rotation + (layoutRandom.NextDouble() - 0.5) * 4;

        var wrapper = new Grid
        {
            Width = frame.Width,
            Height = frame.Height,
            RenderTransformOrigin = new WpfPoint(0.5, 0.5),
            RenderTransform = new RotateTransform(rotation)
        };
        wrapper.Children.Add(frame);

        var centerX = placement.CenterX * canvasWidth;
        var centerY = placement.CenterY * canvasHeight;
        Canvas.SetLeft(wrapper, centerX - frame.Width / 2);
        Canvas.SetTop(wrapper, centerY - frame.Height / 2);
        System.Windows.Controls.Panel.SetZIndex(wrapper, placement.ZIndex);
        PhotoCanvas.Children.Add(wrapper);
    }

    private static List<PhotoPlacement> BuildPlacements(int count)
    {
        return count switch
        {
            2 =>
            [
                new PhotoPlacement(0.35, 0.50, 0.44, -4, 1),
                new PhotoPlacement(0.65, 0.52, 0.44, 4, 2)
            ],
            3 =>
            [
                new PhotoPlacement(0.24, 0.50, 0.34, -6, 2),
                new PhotoPlacement(0.50, 0.50, 0.52, 0, 0),
                new PhotoPlacement(0.76, 0.50, 0.34, 6, 3)
            ],
            4 =>
            [
                new PhotoPlacement(0.26, 0.28, 0.32, -8, 2),
                new PhotoPlacement(0.74, 0.26, 0.34, 7, 3),
                new PhotoPlacement(0.50, 0.50, 0.50, 0, 0),
                new PhotoPlacement(0.26, 0.72, 0.30, -5, 4)
            ],
            _ =>
            [
                new PhotoPlacement(0.27, 0.26, 0.32, -8, 2),
                new PhotoPlacement(0.73, 0.24, 0.32, 8, 3),
                new PhotoPlacement(0.50, 0.50, 0.48, 0, 0),
                new PhotoPlacement(0.27, 0.68, 0.30, -6, 4),
                new PhotoPlacement(0.73, 0.70, 0.32, 5, 5)
            ]
        };
    }

    private static int GetPlacementIndex(int count, int photoIndex) => count switch
    {
        3 => photoIndex switch { 0 => 1, 1 => 0, _ => 2 },
        4 => photoIndex switch { 0 => 2, 1 => 0, 2 => 1, _ => 3 },
        5 => photoIndex switch { 0 => 2, 1 => 0, 2 => 1, 3 => 3, _ => 4 },
        _ => photoIndex
    };

    private static Border CreatePhotoFrame(BitmapImage source, double maxWidth, double maxHeight)
    {
        const double padding = 10;
        var (displayWidth, displayHeight) = FitToBounds(
            source.PixelWidth,
            source.PixelHeight,
            maxWidth - padding * 2,
            maxHeight - padding * 2);

        var image = new System.Windows.Controls.Image
        {
            Source = source,
            Stretch = Stretch.Uniform,
            Width = displayWidth,
            Height = displayHeight,
            HorizontalAlignment = System.Windows.HorizontalAlignment.Center,
            VerticalAlignment = System.Windows.VerticalAlignment.Center
        };

        return new Border
        {
            Background = System.Windows.Media.Brushes.White,
            BorderBrush = new SolidColorBrush(System.Windows.Media.Color.FromRgb(30, 30, 30)),
            BorderThickness = new Thickness(2),
            Padding = new Thickness(padding),
            Width = displayWidth + padding * 2,
            Height = displayHeight + padding * 2,
            Child = image,
            Effect = new DropShadowEffect
            {
                BlurRadius = 18,
                ShadowDepth = 4,
                Opacity = 0.28,
                Direction = 270
            }
        };
    }

    private static (double Width, double Height) FitToBounds(int pixelWidth, int pixelHeight, double maxWidth, double maxHeight)
    {
        if (pixelWidth <= 0 || pixelHeight <= 0)
            return (maxWidth, maxHeight);

        var aspect = pixelWidth / (double)pixelHeight;
        double width;
        double height;

        if (aspect >= maxWidth / maxHeight)
        {
            width = maxWidth;
            height = maxWidth / aspect;
        }
        else
        {
            height = maxHeight;
            width = maxHeight * aspect;
        }

        return (width, height);
    }

    private void SetDisplayName(string displayName)
    {
        var titleCaseName = AnimalNameFormatter.ToTitleCase(displayName);
        var fontSize = displayName.Length switch
        {
            <= 6 => 98,
            <= 10 => 86,
            <= 14 => 74,
            <= 18 => 64,
            _ => 56
        };

        foreach (var outline in new[] { NameOutlineNorth, NameOutlineSouth, NameOutlineEast, NameOutlineWest })
        {
            outline.Text = titleCaseName;
            outline.FontSize = fontSize;
        }

        NameText.Text = titleCaseName;
        NameText.FontSize = fontSize;
    }

    private static BitmapImage? LoadBitmapCached(string path)
    {
        try
        {
            var writeTime = File.GetLastWriteTimeUtc(path).Ticks;
            if (BitmapCache.TryGetValue(path, out var cached) && cached.WriteTimeUtcTicks == writeTime)
                return cached.Image;

            var bitmap = new BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.UriSource = new Uri(path, UriKind.Absolute);
            bitmap.EndInit();
            bitmap.Freeze();

            BitmapCache[path] = (writeTime, bitmap);
            return bitmap;
        }
        catch (Exception ex)
        {
            LogService.Error($"Failed loading image {path}", ex);
            return null;
        }
    }

    public static void ClearBitmapCache() => BitmapCache.Clear();
}
