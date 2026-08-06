using System;
using System.Collections.Generic;
using System.Reflection;
using LitJson;
using UnityEngine;

namespace SixAI.TowerMindPlugin
{
    internal sealed class CommandEnvelope
    {
        public string request_id { get; set; }
        public List<SemanticAction> actions { get; set; }
    }

    internal sealed class SemanticAction
    {
        public string id { get; set; }
        public string type { get; set; }
        public string tower { get; set; }
        public string site_id { get; set; }
        public string tower_id { get; set; }
        public double[] position { get; set; }
    }

    internal sealed class CommandResponse
    {
        public bool ok { get; set; }
        public string request_id { get; set; }
        public List<ActionExecution> results { get; set; }
    }

    internal sealed class ActionExecution
    {
        public string id { get; set; }
        public string type { get; set; }
        public bool success { get; set; }
        public int error_code { get; set; }
        public string message { get; set; }
        public int gold_after { get; set; }
    }

    internal sealed class CommandExecutor
    {
        private readonly MethodInfo _organize =
            typeof(GameLoop).GetMethod(
                "OrganizeAgentActionDescription",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            );
        private readonly MethodInfo _dispatch =
            typeof(GameLoop).GetMethod(
                "DispatchAgentBehavior",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            );

        internal string Execute(string body)
        {
            var request = JsonMapper.ToObject<CommandEnvelope>(body);
            if (request == null || request.actions == null || request.actions.Count == 0)
            {
                throw new ArgumentException("actions must contain at least one semantic action");
            }
            var game = UnityEngine.Object.FindObjectOfType<GameLoop>();
            if (game == null)
            {
                throw new InvalidOperationException("GameLoop is not ready");
            }
            var response = new CommandResponse
            {
                ok = true,
                request_id = request.request_id,
                results = new List<ActionExecution>()
            };
            foreach (var action in request.actions)
            {
                var result = ExecuteOne(game, action);
                response.results.Add(result);
                response.ok = response.ok && result.success;
            }
            return JsonMapper.ToJson(response);
        }

        private ActionExecution ExecuteOne(GameLoop game, SemanticAction action)
        {
            if (action == null || string.IsNullOrEmpty(action.type))
            {
                throw new ArgumentException("action.type is required");
            }
            var behavior = Behavior(action);
            var siteId = ParseSiteId(action.site_id ?? action.tower_id);
            var position = ResolvePosition(game, action, siteId);
            if (behavior == 6)
            {
                return Result(game, action, true, 0, "noop");
            }
            if (behavior <= 5 && siteId < 0)
            {
                return Result(game, action, false, 6, "site_id is required");
            }
            if (behavior == 7 && siteId < 0)
            {
                return Result(game, action, false, 7, "Knight tower site_id is required");
            }

            _organize.Invoke(game, new object[] { position, behavior });
            var knightTowerId = behavior == 7 ? siteId : -1;
            _dispatch.Invoke(
                game,
                new object[] { behavior, siteId, -1, position, knightTowerId }
            );
            var last = game
                .GetLanguageDescriptionCollector()
                .m_structureDescriptionData
                .Agent_Last_Action_Info;
            var success = last != null && last.Is_Success;
            var errorCode = last == null ? -1 : last.Error_Code;
            return Result(
                game,
                action,
                success,
                errorCode,
                success ? "executed by TowerMind" : "rejected by TowerMind"
            );
        }

        private static ActionExecution Result(
            GameLoop game,
            SemanticAction action,
            bool success,
            int errorCode,
            string message
        )
        {
            return new ActionExecution
            {
                id = action.id,
                type = action.type,
                success = success,
                error_code = errorCode,
                message = message,
                gold_after = game.GetCurLevelStatus().CurMoney
            };
        }

        private static int Behavior(SemanticAction action)
        {
            switch (Normalize(action.type))
            {
                case "build":
                    switch (Normalize(action.tower))
                    {
                        case "archer":
                            return 0;
                        case "magician":
                        case "magic":
                        case "mage":
                            return 1;
                        case "knight":
                            return 2;
                        default:
                            throw new ArgumentException("build.tower must be archer, magician, or knight");
                    }
                case "upgrade":
                    return 3;
                case "sell":
                    return 4;
                case "show_range":
                    return 5;
                case "noop":
                    return 6;
                case "relocate_knights":
                    return 7;
                case "deploy_reinforcements":
                    return 8;
                case "move_hero":
                    return 9;
                case "hero_skill":
                    return 10;
                case "upgrade_hero":
                    return 11;
                default:
                    throw new ArgumentException("unsupported action type: " + action.type);
            }
        }

        private static int ParseSiteId(string value)
        {
            int nativeId;
            if (SiteRegistry.TryResolve(value, out nativeId))
            {
                return nativeId;
            }
            if (string.IsNullOrEmpty(value))
            {
                return -1;
            }
            var normalized = Normalize(value)
                .Replace("site_", "")
                .Replace("tower_", "");
            int id;
            return int.TryParse(normalized, out id) ? id : -1;
        }

        private static Vector2 ResolvePosition(
            GameLoop game,
            SemanticAction action,
            int siteId
        )
        {
            if (action.position != null && action.position.Length >= 2)
            {
                return new Vector2((float)action.position[0], (float)action.position[1]);
            }
            if (siteId >= 0 && game.GetTowers() != null && game.GetTowers().ContainsKey(siteId))
            {
                return game.GetTowers()[siteId].transform.position;
            }
            return Vector2.zero;
        }

        private static string Normalize(string value)
        {
            return (value ?? "").Trim().ToLowerInvariant().Replace(" ", "_");
        }
    }
}
