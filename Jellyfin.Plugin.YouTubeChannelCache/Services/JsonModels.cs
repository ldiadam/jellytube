namespace Jellyfin.Plugin.YouTubeChannelCache.Services;

public sealed class CachedChannel
{
    public string ChannelId { get; set; } = string.Empty;

    public string Title { get; set; } = string.Empty;

    public string Description { get; set; } = string.Empty;

    public string Url { get; set; } = string.Empty;

    public string? ThumbnailPath { get; set; }

    public DateTimeOffset LastUpdatedUtc { get; set; }

    public List<CachedVideo> Videos { get; set; } = [];
}

public sealed class CachedVideo
{
    public string VideoId { get; set; } = string.Empty;

    public string Title { get; set; } = string.Empty;

    public string Description { get; set; } = string.Empty;

    public DateTimeOffset? PublishedUtc { get; set; }

    public string? ThumbnailPath { get; set; }

    public string? FilePath { get; set; }

    public long? DurationSeconds { get; set; }
}
