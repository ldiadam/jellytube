using Jellyfin.Plugin.YouTubeChannelCache.Services;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Providers;

namespace Jellyfin.Plugin.YouTubeChannelCache.Providers;

public sealed class YouTubeChannelMetadataProvider : IRemoteMetadataProvider<Series, SeriesInfo>
{
    public const string ProviderKey = "YouTube";

    private readonly CacheStore _cacheStore;

    public YouTubeChannelMetadataProvider(CacheStore cacheStore)
    {
        _cacheStore = cacheStore;
    }

    public string Name => "YouTube Channel Cache";

    public async Task<MetadataResult<Series>> GetMetadata(SeriesInfo info, CancellationToken cancellationToken)
    {
        var result = new MetadataResult<Series>();
        if (!info.ProviderIds.TryGetValue(ProviderKey, out var channelId) || string.IsNullOrWhiteSpace(channelId))
        {
            return result;
        }

        var cached = await _cacheStore.LoadChannelAsync(channelId, cancellationToken).ConfigureAwait(false);
        if (cached is null)
        {
            return result;
        }

        result.HasMetadata = true;
        result.Item = new Series
        {
            Name = cached.Title,
            Overview = cached.Description
        };

        result.Item.ProviderIds[ProviderKey] = cached.ChannelId;

        return result;
    }

    public Task<IEnumerable<RemoteSearchResult>> GetSearchResults(SeriesInfo searchInfo, CancellationToken cancellationToken)
    {
        return Task.FromResult(Enumerable.Empty<RemoteSearchResult>());
    }

    public Task<HttpResponseMessage> GetImageResponse(string url, CancellationToken cancellationToken)
    {
        throw new NotSupportedException("Images are resolved from Jellyfin local paths, not remote provider URLs.");
    }
}
