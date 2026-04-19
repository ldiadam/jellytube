using Jellyfin.Plugin.YouTubeChannelCache.Services;
using MediaBrowser.Model.Tasks;

namespace Jellyfin.Plugin.YouTubeChannelCache.ScheduledTasks;

public sealed class RefreshYouTubeCacheTask : IScheduledTask
{
    private readonly ChannelCacheService _channelCacheService;

    public RefreshYouTubeCacheTask(ChannelCacheService channelCacheService)
    {
        _channelCacheService = channelCacheService;
    }

    public string Name => "Refresh YouTube Channel Cache";

    public string Key => "RefreshYouTubeChannelCache";

    public string Description => "Refreshes cached YouTube channel metadata using yt-dlp.";

    public string Category => "Library";

    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        var config = Plugin.Instance!.Configuration;
        if (!config.EnableScheduledRefresh)
        {
            return [];
        }

        return
        [
            new TaskTriggerInfo
            {
                Type = TaskTriggerInfoType.IntervalTrigger,
                IntervalTicks = TimeSpan.FromMinutes(config.RefreshIntervalMinutes).Ticks
            }
        ];
    }

    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        progress.Report(5);
        await _channelCacheService.RefreshAllAsync(cancellationToken).ConfigureAwait(false);
        progress.Report(100);
    }
}
