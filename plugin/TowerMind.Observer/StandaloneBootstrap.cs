using UnityEngine;

namespace SixAI.TowerMindPlugin
{
    public static class StandaloneBootstrap
    {
        private static bool _installed;
        private static ObserverRuntime _runtime;

        public static void Install()
        {
            if (_installed)
            {
                return;
            }
            _installed = true;
            var host = new GameObject("[SixAI] TowerMind Observer");
            Object.DontDestroyOnLoad(host);
            _runtime = host.AddComponent<ObserverRuntime>();
            RuntimeLog.Info("standalone bootstrap installed");
        }

        public static void Refresh()
        {
            if (_runtime != null)
            {
                _runtime.RefreshNow();
            }
        }
    }
}
