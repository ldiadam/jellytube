using System.Text.Json;

namespace Jellyfin.Plugin.YouTubeChannelCache.Services;

public sealed class CacheStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public string GetRoot()
    {
        return Plugin.Instance!.Configuration.CacheDirectory;
    }

    public string GetChannelDirectory(string channelId)
    {
        return Path.Combine(GetRoot(), channelId);
    }

    public string GetChannelJsonPath(string channelId)
    {
        return Path.Combine(GetChannelDirectory(channelId), "channel.json");
    }

    public async Task SaveChannelAsync(CachedChannel channel, CancellationToken cancellationToken)
    {
        var dir = GetChannelDirectory(channel.ChannelId);
        Directory.CreateDirectory(dir);

        var path = GetChannelJsonPath(channel.ChannelId);
        await using var stream = File.Create(path);
        await JsonSerializer.SerializeAsync(stream, channel, _jsonOptions, cancellationToken);
    }

    public async Task<CachedChannel?> LoadChannelAsync(string channelId, CancellationToken cancellationToken)
    {
        var path = GetChannelJsonPath(channelId);
        if (!File.Exists(path))
        {
            return null;
        }

        await using var stream = File.OpenRead(path);
        return await JsonSerializer.DeserializeAsync<CachedChannel>(stream, _jsonOptions, cancellationToken);
    }

    public IEnumerable<string> GetKnownChannelIds()
    {
        var root = GetRoot();
        if (!Directory.Exists(root))
        {
            return [];
        }

        return Directory.EnumerateDirectories(root)
            .Select(Path.GetFileName)
            .OfType<string>()
            .Where(static x => !string.IsNullOrWhiteSpace(x));
    }
}
