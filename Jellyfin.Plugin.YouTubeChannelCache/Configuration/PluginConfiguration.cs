using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.YouTubeChannelCache.Configuration;

public class PluginConfiguration : BasePluginConfiguration
{
    public string CacheDirectory { get; set; } = "/cache/youtube-channels";

    public bool EnableScheduledRefresh { get; set; } = true;

    public int RefreshIntervalMinutes { get; set; } = 360;

    public bool DownloadMissingMetadataOnly { get; set; } = true;

    public string YtDlpPath { get; set; } = "yt-dlp";

    public List<string> ChannelUrls { get; set; } = [];
}
