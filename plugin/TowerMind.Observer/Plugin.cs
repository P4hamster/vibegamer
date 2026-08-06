using BepInEx;
using BepInEx.Logging;

namespace SixAI.TowerMindPlugin
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    public sealed class ObserverPlugin : BaseUnityPlugin
    {
        public const string PluginGuid = "com.sixai.towermind.observer";
        public const string PluginName = "TowerMind Observer";
        public const string PluginVersion = "0.1.0";

        internal static ManualLogSource Log;

        private void Awake()
        {
            Log = Logger;
            gameObject.AddComponent<ObserverRuntime>();
            Logger.LogInfo("TowerMind Observer runtime attached");
        }
    }
}
