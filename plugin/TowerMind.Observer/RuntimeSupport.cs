using System;
using System.IO;
using System.Reflection;
using UnityEngine;

namespace SixAI.TowerMindPlugin
{
    internal static class RuntimeConstants
    {
        internal const string Version = "0.3.2";
        internal const int DefaultObserverPort = 17871;
        internal const string ObserverPortEnvironment = "TOWERMIND_OBSERVER_PORT";
    }

    internal static class RuntimeLog
    {
        internal static void Info(string message)
        {
            Debug.Log("[TowerMind.Observer] " + message);
        }

        internal static void Warning(string message)
        {
            Debug.LogWarning("[TowerMind.Observer] " + message);
        }
    }

    internal sealed class ObserverRuntime : MonoBehaviour
    {
        private BridgeServer _server;
        private StateProjector _projector;
        private CommandExecutor _commands;
        private float _nextSnapshotAt;
        private GUIStyle _boxStyle;
        private GUIStyle _hudFrameStyle;
        private GUIStyle _hudCardStyle;
        private GUIStyle _hudTitleStyle;
        private GUIStyle _hudSectionStyle;
        private GUIStyle _hudBodyStyle;
        private GUIStyle _titleStyle;
        private GUIStyle _bodyStyle;
        private GUIStyle _scrimStyle;
        private GUIStyle _transitionBoxStyle;
        private GUIStyle _transitionTitleStyle;
        private GUIStyle _transitionBodyStyle;
        private GUIStyle _buttonStyle;
        private Texture2D _hudBackground;
        private Vector2 _hudScrollPosition;

        private void Awake()
        {
            TelemetryStore.Reset();
            _projector = new StateProjector();
            _commands = new CommandExecutor();
            var port = ResolveObserverPort();
            _server = new BridgeServer(port);
            _server.SetMechanics(LoadMechanics());
            _server.Start();
            RuntimeLog.Info("runtime started on http://127.0.0.1:" + port + "/");
        }

        private static int ResolveObserverPort()
        {
            var raw = Environment.GetEnvironmentVariable(
                RuntimeConstants.ObserverPortEnvironment
            );
            int port;
            if (int.TryParse(raw, out port) && port >= 1024 && port <= 65535)
            {
                return port;
            }
            if (!string.IsNullOrEmpty(raw))
            {
                RuntimeLog.Warning(
                    "Invalid TOWERMIND_OBSERVER_PORT; using "
                    + RuntimeConstants.DefaultObserverPort
                );
            }
            return RuntimeConstants.DefaultObserverPort;
        }

        internal void RefreshNow()
        {
            if (_server == null || _projector == null)
            {
                return;
            }
            try
            {
                _server.SetState(_projector.Capture());
            }
            catch (Exception exc)
            {
                _server.SetState(
                    JsonUtil.Error("state_unavailable", exc.Message)
                );
            }
        }

        private void Update()
        {
            PendingCommand pending;
            while (_server != null && _server.TryDequeueCommand(out pending))
            {
                try
                {
                    pending.result = _commands.Execute(pending.body);
                    pending.statusCode = 200;
                }
                catch (Exception exc)
                {
                    pending.result = JsonUtil.Error("command_failed", exc.Message);
                    pending.statusCode = 400;
                    RuntimeLog.Warning("Command failed: " + exc);
                }
                finally
                {
                    pending.completed.Set();
                }
            }

            if (_server != null && Time.realtimeSinceStartup >= _nextSnapshotAt)
            {
                _nextSnapshotAt = Time.realtimeSinceStartup + 0.1f;
                RefreshNow();
            }
        }

        private static string LoadMechanics()
        {
            var assemblyDirectory = Path.GetDirectoryName(
                Assembly.GetExecutingAssembly().Location
            );
            var candidates = new[]
            {
                Path.Combine(Application.streamingAssetsPath, "TowerMind.Observer", "mechanics.json"),
                Path.Combine(assemblyDirectory ?? "", "TowerMind.Observer", "mechanics.json"),
                Path.Combine(assemblyDirectory ?? "", "mechanics.json")
            };
            foreach (var path in candidates)
            {
                if (File.Exists(path))
                {
                    return File.ReadAllText(path);
                }
            }
            return JsonUtil.Error(
                "mechanics_missing",
                "mechanics.json has not been installed"
            );
        }

        private void OnGUI()
        {
            if (_server == null)
            {
                return;
            }
            // TowerMind also uses immediate-mode GUI. A strongly negative
            // depth keeps the observer/HUD above the game's own OnGUI layers.
            GUI.depth = -10000;
            var overlay = _server.GetDecision();
            if (overlay == null || string.IsNullOrEmpty(overlay.analysis_summary))
            {
                return;
            }
            EnsureStyles();
            if (string.Equals(overlay.view, "transition", StringComparison.OrdinalIgnoreCase))
            {
                DrawTransition(overlay);
                return;
            }
            DrawHudBackground();
            DrawCommanderCard(overlay);
        }

        private void DrawHudBackground()
        {
            if (_hudBackground == null)
            {
                return;
            }
            // The game camera is square and centered in the wide recording
            // layout. Paint only the two letterbox bands so the generated
            // background never covers the live game viewport or its HUD.
            var playfieldSize = Mathf.Min(Screen.width, Screen.height);
            var sideWidth = (Screen.width - playfieldSize) / 2f;
            if (sideWidth < 224f)
            {
                return;
            }
            GUI.DrawTexture(
                new Rect(0f, 0f, sideWidth, Screen.height),
                _hudBackground,
                ScaleMode.ScaleAndCrop
            );
            GUI.DrawTexture(
                new Rect(Screen.width - sideWidth, 0f, sideWidth, Screen.height),
                _hudBackground,
                ScaleMode.ScaleAndCrop
            );
        }

        private void DrawCommanderCard(DecisionOverlay overlay)
        {
            var playfieldSize = Mathf.Min(Screen.width, Screen.height);
            var sideWidth = (Screen.width - playfieldSize) / 2f;
            if (sideWidth < 224f)
            {
                // Never cover the game's own viewport just to show the card.
                return;
            }
            var cardWidth = Mathf.Min(260f, sideWidth - 28f);
            var card = new Rect(14f, 14f, cardWidth, Screen.height - 28f);
            GUI.Box(card, GUIContent.none, _hudFrameStyle);
            var inner = new Rect(
                card.x + 2f,
                card.y + 2f,
                card.width - 4f,
                card.height - 4f
            );
            GUI.Box(inner, GUIContent.none, _hudCardStyle);

            var contentX = inner.x + 14f;
            var contentWidth = inner.width - 28f;
            var cursorY = inner.y + 14f;
            GUI.Label(
                new Rect(contentX, cursorY, contentWidth, 28f),
                "AI 指挥官 · " + (overlay.model ?? "未命名"),
                _hudTitleStyle
            );
            cursorY += 36f;

            string immediateActions;
            string standingOrders;
            SplitActionText(overlay.action_text, out immediateActions, out standingOrders);
            var viewport = new Rect(
                contentX,
                cursorY,
                contentWidth,
                Mathf.Max(40f, inner.yMax - cursorY - 12f)
            );
            var contentHeight = HudContentHeight(
                overlay.analysis_summary,
                immediateActions,
                standingOrders,
                contentWidth
            );
            _hudScrollPosition = GUI.BeginScrollView(
                viewport,
                _hudScrollPosition,
                new Rect(0f, 0f, contentWidth, contentHeight),
                false,
                true
            );
            cursorY = 8f;
            cursorY = DrawHudSection(
                "当前判断",
                overlay.analysis_summary,
                0f,
                cursorY,
                contentWidth
            );
            cursorY = DrawHudSection(
                "行动",
                immediateActions,
                0f,
                cursorY,
                contentWidth
            );
            DrawHudSection(
                "长期策略",
                standingOrders,
                0f,
                cursorY,
                contentWidth
            );
            GUI.EndScrollView();
        }

        private float HudContentHeight(
            string analysis,
            string immediate,
            string standing,
            float width
        )
        {
            var height = 8f;
            height = HudSectionHeight(height, analysis, width);
            height = HudSectionHeight(height, immediate, width);
            height = HudSectionHeight(height, standing, width);
            return Mathf.Max(40f, height + 8f);
        }

        private float HudSectionHeight(float y, string text, float width)
        {
            if (string.IsNullOrWhiteSpace(text))
            {
                return y;
            }
            var height = Mathf.Max(
                24f,
                _hudBodyStyle.CalcHeight(new GUIContent(text), width)
            );
            return y + 26f + height + 14f;
        }

        private float DrawHudSection(
            string heading,
            string text,
            float x,
            float y,
            float width
        )
        {
            if (string.IsNullOrWhiteSpace(text))
            {
                return y;
            }
            GUI.Label(
                new Rect(x, y, width, 24f),
                heading,
                _hudSectionStyle
            );
            y += 26f;
            var height = Mathf.Max(
                24f,
                _hudBodyStyle.CalcHeight(new GUIContent(text), width)
            );
            GUI.Label(
                new Rect(x, y, width, height),
                text,
                _hudBodyStyle
            );
            return y + height + 14f;
        }

        private static void SplitActionText(
            string actionText,
            out string immediateActions,
            out string standingOrders
        )
        {
            var text = actionText ?? "";
            var marker = text.IndexOf("长期：", StringComparison.Ordinal);
            if (marker < 0)
            {
                immediateActions = text;
                standingOrders = "";
                return;
            }
            immediateActions = text.Substring(0, marker).Trim(' ', '；');
            standingOrders = text.Substring(marker).Trim();
        }

        private void DrawTransition(DecisionOverlay overlay)
        {
            var success = string.Equals(
                overlay.outcome,
                "success",
                StringComparison.OrdinalIgnoreCase
            );
            GUI.Box(
                new Rect(0f, 0f, Screen.width, Screen.height),
                GUIContent.none,
                _scrimStyle
            );
            var width = Math.Min(760f, Screen.width - 48f);
            var height = 330f;
            var left = (Screen.width - width) / 2f;
            var top = (Screen.height - height) / 2f;
            GUI.Box(
                new Rect(left, top, width, height),
                GUIContent.none,
                _transitionBoxStyle
            );
            _transitionTitleStyle.normal.textColor = success
                ? new Color(0.35f, 1f, 0.68f)
                : new Color(1f, 0.38f, 0.4f);
            GUI.Label(
                new Rect(left + 32f, top + 40f, width - 64f, 86f),
                overlay.analysis_summary,
                _transitionTitleStyle
            );
            GUI.Label(
                new Rect(left + 52f, top + 132f, width - 104f, 72f),
                overlay.action_text,
                _transitionBodyStyle
            );
            if (success)
            {
                if (GUI.Button(
                    new Rect(left + width / 2f - 110f, top + 236f, 220f, 58f),
                    "下一关",
                    _buttonStyle
                ))
                {
                    _server.SetTransitionAction("next");
                }
                return;
            }
            if (overlay.can_retry)
            {
                if (GUI.Button(
                    new Rect(left + width / 2f - 238f, top + 236f, 220f, 58f),
                    "再试一次",
                    _buttonStyle
                ))
                {
                    _server.SetTransitionAction("retry");
                }
                if (GUI.Button(
                    new Rect(left + width / 2f + 18f, top + 236f, 220f, 58f),
                    "停止",
                    _buttonStyle
                ))
                {
                    _server.SetTransitionAction("stop");
                }
            }
            else if (GUI.Button(
                new Rect(left + width / 2f - 110f, top + 236f, 220f, 58f),
                "停止",
                _buttonStyle
            ))
            {
                _server.SetTransitionAction("stop");
            }
        }

        private void EnsureStyles()
        {
            if (_boxStyle != null)
            {
                return;
            }
            Font font = null;
            try
            {
                // Arial Unicode is bundled with current macOS releases and
                // covers the Chinese HUD text. The array overload repeatedly
                // retried an unavailable PingFang face in Unity 2023.
                font = Font.CreateDynamicFontFromOSFont(
                    "Arial Unicode MS",
                    20
                );
            }
            catch (Exception exc)
            {
                RuntimeLog.Warning("HUD font fallback: " + exc.Message);
            }
            if (font == null)
            {
                font = GUI.skin.label.font;
            }
            _hudFrameStyle = new GUIStyle(GUI.skin.box);
            _hudFrameStyle.normal.background = TextureFactory.Solid(
                new Color(0.1f, 0.75f, 0.82f, 0.9f)
            );
            _hudCardStyle = new GUIStyle(GUI.skin.box);
            _hudCardStyle.normal.background = TextureFactory.Solid(
                new Color(0.025f, 0.055f, 0.1f, 0.94f)
            );
            _hudTitleStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 18,
                fontStyle = FontStyle.Bold,
                wordWrap = true,
                clipping = TextClipping.Overflow
            };
            _hudTitleStyle.normal.textColor = new Color(0.36f, 0.9f, 1f);
            _hudSectionStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 15,
                fontStyle = FontStyle.Bold,
                wordWrap = true,
                clipping = TextClipping.Overflow
            };
            _hudSectionStyle.normal.textColor = new Color(0.36f, 0.9f, 1f);
            _hudBodyStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 14,
                wordWrap = true,
                clipping = TextClipping.Overflow,
                padding = new RectOffset(0, 0, 0, 0)
            };
            _hudBodyStyle.normal.textColor = Color.white;
            _boxStyle = new GUIStyle(GUI.skin.box);
            _boxStyle.normal.background = TextureFactory.Solid(
                new Color(0.03f, 0.05f, 0.09f, 0.88f)
            );
            _titleStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 20,
                fontStyle = FontStyle.Bold
            };
            _titleStyle.normal.textColor = new Color(0.36f, 0.9f, 1f);
            _bodyStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 15,
                wordWrap = true
            };
            _bodyStyle.normal.textColor = Color.white;
            _scrimStyle = new GUIStyle(GUI.skin.box);
            _scrimStyle.normal.background = TextureFactory.Solid(
                new Color(0.01f, 0.015f, 0.03f, 0.74f)
            );
            _transitionBoxStyle = new GUIStyle(GUI.skin.box);
            _transitionBoxStyle.normal.background = TextureFactory.Solid(
                new Color(0.035f, 0.06f, 0.11f, 0.97f)
            );
            _transitionTitleStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 56,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter
            };
            _transitionBodyStyle = new GUIStyle(GUI.skin.label)
            {
                font = font,
                fontSize = 24,
                wordWrap = true,
                alignment = TextAnchor.MiddleCenter
            };
            _transitionBodyStyle.normal.textColor = Color.white;
            _buttonStyle = new GUIStyle(GUI.skin.button)
            {
                font = font,
                fontSize = 23,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter
            };
            _buttonStyle.normal.textColor = Color.white;
            _hudBackground = LoadHudBackground();
        }

        private static Texture2D LoadHudBackground()
        {
            var assemblyDirectory = Path.GetDirectoryName(
                Assembly.GetExecutingAssembly().Location
            );
            var candidates = new[]
            {
                Path.Combine(
                    Application.streamingAssetsPath,
                    "TowerMind.Observer",
                    "hud_background.png"
                ),
                Path.Combine(assemblyDirectory ?? "", "hud_background.png"),
                Path.Combine(assemblyDirectory ?? "", "TowerMind.Observer", "hud_background.png")
            };
            foreach (var path in candidates)
            {
                try
                {
                    if (!File.Exists(path))
                    {
                        continue;
                    }
                    var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                    if (texture.LoadImage(File.ReadAllBytes(path)))
                    {
                        texture.wrapMode = TextureWrapMode.Clamp;
                        return texture;
                    }
                    UnityEngine.Object.Destroy(texture);
                }
                catch (Exception exc)
                {
                    RuntimeLog.Warning("HUD background load failed: " + exc.Message);
                }
            }
            RuntimeLog.Warning("HUD background asset not found; using game letterbox background");
            return null;
        }

        private void OnDestroy()
        {
            if (_server != null)
            {
                _server.Stop();
            }
        }
    }

    internal static class TextureFactory
    {
        internal static Texture2D Solid(Color color)
        {
            var texture = new Texture2D(1, 1);
            texture.SetPixel(0, 0, color);
            texture.Apply();
            return texture;
        }
    }
}
