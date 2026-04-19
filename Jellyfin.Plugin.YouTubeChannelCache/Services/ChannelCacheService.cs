using System.Diagnostics;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.YouTubeChannelCache.Services;

public sealed class ChannelCacheService
{
    private readonly CacheStore _cacheStore;
    private readonly ILogger<ChannelCacheService> _logger;

    public ChannelCacheService(CacheStore cacheStore, ILogger<ChannelCacheService> logger)
    {
        _cacheStore = cacheStore;
        _logger = logger;
    }

    public async Task RefreshAllAsync(CancellationToken cancellationToken)
    {
        foreach (var channelUrl in Plugin.Instance!.Configuration.ChannelUrls)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (string.IsNullOrWhiteSpace(channelUrl))
            {
                continue;
            }

            await RefreshChannelAsync(channelUrl, cancellationToken).ConfigureAwait(false);
        }
    }

    public async Task RefreshChannelAsync(string channelUrl, CancellationToken cancellationToken)
    {
        var ytDlp = Plugin.Instance!.Configuration.YtDlpPath;

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = ytDlp,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            psi.ArgumentList.Add("--dump-single-json");
            psi.ArgumentList.Add("--flat-playlist");
            psi.ArgumentList.Add("--playlist-end");
            psi.ArgumentList.Add("100");
            psi.ArgumentList.Add(channelUrl);

            using var process = new Process { StartInfo = psi };
            process.Start();

            var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
            var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
            await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);

            var stdout = await stdoutTask.ConfigureAwait(false);
            var stderr = await stderrTask.ConfigureAwait(false);

            if (process.ExitCode != 0)
            {
                throw new InvalidOperationException($"yt-dlp failed with exit code {process.ExitCode}: {stderr}");
            }

            using var doc = JsonDocument.Parse(stdout);
            var root = doc.RootElement;

            var channel = new CachedChannel
            {
                ChannelId = GetString(root, "channel_id", "unknown"),
                Title = GetString(root, "title"),
                Description = GetString(root, "description"),
                Url = channelUrl,
                ThumbnailPath = GetThumbnailUrl(root),
                LastUpdatedUtc = DateTimeOffset.UtcNow,
                Videos = []
            };

            if (root.TryGetProperty("entries", out var entries) && entries.ValueKind == JsonValueKind.Array)
            {
                foreach (var entry in entries.EnumerateArray())
                {
                    channel.Videos.Add(new CachedVideo
                    {
                        VideoId = GetString(entry, "id"),
                        Title = GetString(entry, "title"),
                        Description = GetString(entry, "description"),
                        PublishedUtc = GetPublishedUtc(entry),
                        ThumbnailPath = GetThumbnailUrl(entry),
                        DurationSeconds = GetInt64(entry, "duration")
                    });
                }
            }

            await _cacheStore.SaveChannelAsync(channel, cancellationToken).ConfigureAwait(false);
            _logger.LogInformation(
                "Refreshed YouTube cache for channel {ChannelId} ({Title})",
                channel.ChannelId,
                channel.Title);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to refresh YouTube channel cache for {ChannelUrl}", channelUrl);
            throw;
        }
    }

    private static DateTimeOffset? GetPublishedUtc(JsonElement element)
    {
        if (element.TryGetProperty("timestamp", out var timestamp)
            && timestamp.ValueKind == JsonValueKind.Number
            && timestamp.TryGetInt64(out var timestampSeconds))
        {
            return DateTimeOffset.FromUnixTimeSeconds(timestampSeconds);
        }

        return null;
    }

    private static long? GetInt64(JsonElement element, string propertyName)
    {
        return element.TryGetProperty(propertyName, out var value)
            && value.ValueKind == JsonValueKind.Number
            && value.TryGetInt64(out var result)
                ? result
                : null;
    }

    private static string GetString(JsonElement element, string propertyName, string fallback = "")
    {
        return element.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback
            : fallback;
    }

    private static string? GetThumbnailUrl(JsonElement element)
    {
        if (element.TryGetProperty("thumbnail", out var thumbnail) && thumbnail.ValueKind == JsonValueKind.String)
        {
            return thumbnail.GetString();
        }

        if (!element.TryGetProperty("thumbnails", out var thumbnails) || thumbnails.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        return thumbnails.EnumerateArray()
            .Select(static x => GetString(x, "url"))
            .LastOrDefault(static x => !string.IsNullOrWhiteSpace(x));
    }
}
