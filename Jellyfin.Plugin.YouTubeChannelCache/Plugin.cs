using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.YouTubeChannelCache;

public sealed class Plugin : BasePlugin<Configuration.PluginConfiguration>, IHasWebPages
{
    public static Plugin? Instance { get; private set; }

    public override string Name => "YouTube Channel Cache";

    public override Guid Id => Guid.Parse("5d3f0fcb-4412-4f8f-b7b6-d7ab2cd2a101");

    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public IEnumerable<PluginPageInfo> GetPages()
    {
        return
        [
            new PluginPageInfo
            {
                Name = "youtubechannelcache",
                EmbeddedResourcePath = $"{GetType().Namespace}.Web.configPage.html"
            }
        ];
    }
}
