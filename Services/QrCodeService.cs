using System.IO;
using System.Windows.Media.Imaging;
using QRCoder;

namespace ShelterPetViewer.Services;

public static class QrCodeService
{
    public static string GetAnimalUrl(string uniqueId) =>
        $"https://new.shelterluv.com/embed/animal/{Uri.EscapeDataString(uniqueId)}";

    public static BitmapSource CreateQrCode(string url, int pixelsPerModule = 5)
    {
        using var generator = new QRCodeGenerator();
        using var data = generator.CreateQrCode(url, QRCodeGenerator.ECCLevel.Q);
        var png = new PngByteQRCode(data);
        var bytes = png.GetGraphic(pixelsPerModule);

        using var stream = new MemoryStream(bytes);
        var image = new BitmapImage();
        image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.StreamSource = stream;
        image.EndInit();
        image.Freeze();
        return image;
    }
}
