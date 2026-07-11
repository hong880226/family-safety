using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using FsCommon;

namespace FsAgent;

/// <summary>
/// Captures the primary screen as a JPEG using System.Drawing.Common (GDI+).
/// This is the v1 backend; v2 should use DXGI Desktop Duplication for
/// reliable capture across all apps (some fullscreen exclusive apps go
/// black under GDI+).
///
/// PRIVACY (architecture §5.3): only invoked when the backend has queued a
/// screenshot command. We always notify FsTray first (toast + brief delay)
/// so the child sees "家长正在查看你的桌面" before the shutter fires.
/// The bytes travel over Bearer-authenticated HTTPS to the backend.
/// </summary>
public static class ScreenshotCapture
{
    public static byte[]? CapturePrimaryScreenJpeg(int quality = 60)
    {
        try
        {
            var bounds = System.Windows.Forms.Screen.PrimaryScreen?.Bounds
                         ?? new Rectangle(0, 0, 1920, 1080);

            using var bmp = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
            }

            using var ms = new MemoryStream();
            var encoder = ImageCodecInfo.GetImageEncoders()
                .FirstOrDefault(c => c.FormatID == ImageFormat.Jpeg.Guid);
            if (encoder == null)
            {
                Logger.Error(ProcessNames.Agent, "JPEG encoder missing");
                return null;
            }

            var p = new EncoderParameters(1);
            p.Param[0] = new EncoderParameter(Encoder.Quality, (long)quality);
            bmp.Save(ms, encoder, p);
            return ms.ToArray();
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Agent, $"ScreenshotCapture failed: {ex.Message}");
            return null;
        }
    }
}
