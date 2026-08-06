using System;
using System.Collections.Generic;
using LitJson;

namespace SixAI.TowerMindPlugin
{
    internal sealed class TelemetryEvent
    {
        public long seq { get; set; }
        public string type { get; set; }
        public double game_time { get; set; }
        public Dictionary<string, object> detail { get; set; }
    }

    internal sealed class TelemetryEnvelope
    {
        public long latest_seq { get; set; }
        public List<TelemetryEvent> events { get; set; }
    }

    internal sealed class TelemetrySummary
    {
        public long latest_seq { get; set; }
        public long enemy_damage { get; set; }
        public long hero_damage_taken { get; set; }
        public long knight_damage_taken { get; set; }
        public int enemy_kills { get; set; }
        public int leaks { get; set; }
        public int tower_builds { get; set; }
        public int tower_upgrades { get; set; }
        public int tower_sales { get; set; }
        public Dictionary<string, int> leaks_by_type { get; set; }
        public CompletedTelemetry last_completed { get; set; }
    }

    internal sealed class CompletedTelemetry
    {
        public long enemy_damage { get; set; }
        public long hero_damage_taken { get; set; }
        public long knight_damage_taken { get; set; }
        public int enemy_kills { get; set; }
        public int leaks { get; set; }
        public int tower_builds { get; set; }
        public int tower_upgrades { get; set; }
        public int tower_sales { get; set; }
        public Dictionary<string, int> leaks_by_type { get; set; }
    }

    public static class TelemetryStore
    {
        private const int MaxEvents = 4000;
        private static readonly object Gate = new object();
        private static readonly List<TelemetryEvent> Events = new List<TelemetryEvent>();
        private static long _seq;
        private static long _enemyDamage;
        private static long _heroDamage;
        private static long _knightDamage;
        private static int _kills;
        private static int _leaks;
        private static int _builds;
        private static int _upgrades;
        private static int _sales;
        private static readonly Dictionary<string, int> _leaksByType =
            new Dictionary<string, int>();
        private static string _lastConfirmedAction = "";
        private static CompletedTelemetry _lastCompleted;

        public static void Reset()
        {
            lock (Gate)
            {
                Events.Clear();
                _seq = 0;
                _enemyDamage = 0;
                _heroDamage = 0;
                _knightDamage = 0;
                _kills = 0;
                _leaks = 0;
                _builds = 0;
                _upgrades = 0;
                _sales = 0;
                _leaksByType.Clear();
                _lastConfirmedAction = "";
            }
        }

        public static void EpisodeStarted()
        {
            Reset();
            SiteRegistry.Reset();
            Add("episode_started", null);
        }

        public static void DamageFromAttack(Character target, int attackValue)
        {
            var before = target == null ? 0 : target.GetCurHealth();
            var after = Math.Max(0, before + attackValue);
            Damage(target, before, after);
        }

        internal static void Damage(Character target, int before, int after)
        {
            var amount = Math.Max(0, before - after);
            if (amount <= 0)
            {
                return;
            }
            var kind = "unit";
            lock (Gate)
            {
                if (target is Enemy)
                {
                    kind = "enemy";
                    _enemyDamage += amount;
                    if (before > 0 && after == 0)
                    {
                        _kills++;
                    }
                }
                else if (target is Hero)
                {
                    kind = "hero";
                    _heroDamage += amount;
                }
                else if (target is Knight)
                {
                    kind = "knight";
                    _knightDamage += amount;
                }
            }
            Add(
                "damage",
                new Dictionary<string, object>
                {
                    { "target_kind", kind },
                    { "target_id", target.GetInstanceID() },
                    { "amount", amount },
                    { "health_after", after }
                }
            );
            if (target is Enemy && before > 0 && after == 0)
            {
                Add(
                    "enemy_killed",
                    new Dictionary<string, object>
                    {
                        { "enemy_id", target.GetInstanceID() },
                        { "enemy_type", ((Enemy)target).GetEnemyType().ToString() }
                    }
                );
            }
        }

        public static void Leak(Enemy enemy)
        {
            var enemyType = EnemyName(enemy);
            lock (Gate)
            {
                _leaks++;
                if (!_leaksByType.ContainsKey(enemyType))
                {
                    _leaksByType[enemyType] = 0;
                }
                _leaksByType[enemyType]++;
            }
            Add(
                "enemy_leaked",
                new Dictionary<string, object>
                {
                    { "enemy_id", enemy.GetInstanceID() },
                    { "enemy_type", enemyType },
                    { "health", enemy.GetCurHealth() }
                }
            );
        }

        private static string EnemyName(Enemy enemy)
        {
            if (enemy == null)
            {
                return "Unknown";
            }
            try
            {
                var game = UnityEngine.Object.FindObjectOfType<GameLoop>();
                if (game != null)
                {
                    var info = game.GetEnemyInfo(enemy.GetEnemyType());
                    if (info != null && !string.IsNullOrEmpty(info.Name))
                    {
                        return info.Name;
                    }
                }
            }
            catch
            {
                // Keep telemetry non-fatal if a scene is being torn down.
            }
            return enemy.GetEnemyType().ToString();
        }

        public static void ActionConfirmed(GameLoop game)
        {
            if (
                game == null
                || game.GetLanguageDescriptionCollector() == null
                || game.GetLanguageDescriptionCollector().m_structureDescriptionData == null
            )
            {
                return;
            }
            var official = game
                .GetLanguageDescriptionCollector()
                .m_structureDescriptionData;
            var last = official.Agent_Last_Action_Info;
            if (last == null || !last.Is_Success)
            {
                return;
            }
            var position = last.Position;
            var signature =
                official.Level_Current_Step
                + ":"
                + last.Action_Index
                + ":"
                + (position == null ? "" : position.X + "," + position.Y);
            lock (Gate)
            {
                if (signature == _lastConfirmedAction)
                {
                    return;
                }
                _lastConfirmedAction = signature;
                if (last.Action_Index >= 0 && last.Action_Index <= 2)
                {
                    _builds++;
                }
                else if (last.Action_Index == 3)
                {
                    _upgrades++;
                }
                else if (last.Action_Index == 4)
                {
                    _sales++;
                }
            }
            Add(
                "action_confirmed",
                new Dictionary<string, object>
                {
                    { "action_index", last.Action_Index },
                    { "x", position == null ? 0 : position.X },
                    { "y", position == null ? 0 : position.Y },
                    { "gold_after", game.GetCurLevelStatus().CurMoney }
                }
            );
        }

        public static void GameOver(GameLoop game)
        {
            if (game == null || game.GetCurLevelStatus() == null)
            {
                return;
            }
            var status = game.GetCurLevelStatus();
            lock (Gate)
            {
                _lastCompleted = new CompletedTelemetry
                {
                    enemy_damage = _enemyDamage,
                    hero_damage_taken = _heroDamage,
                    knight_damage_taken = _knightDamage,
                    enemy_kills = _kills,
                    leaks = _leaks,
                    tower_builds = _builds,
                    tower_upgrades = _upgrades,
                    tower_sales = _sales,
                    leaks_by_type = new Dictionary<string, int>(_leaksByType)
                };
            }
            Add(
                "game_over",
                new Dictionary<string, object>
                {
                    { "life", status.CurLife },
                    { "waves_remaining", status.CurWave },
                    { "gold", status.CurMoney }
                }
            );
        }

        internal static void TowerAction(string type, Tower tower)
        {
            lock (Gate)
            {
                if (type == "tower_built")
                {
                    _builds++;
                }
                else if (type == "tower_upgraded")
                {
                    _upgrades++;
                }
                else if (type == "tower_sold")
                {
                    _sales++;
                }
            }
            Add(
                type,
                new Dictionary<string, object>
                {
                    { "site_id", "site_" + tower.GetTowerID().ToString("D2") },
                    { "tower_type", tower.m_towerType.ToString() },
                    { "tower_level", tower.GetTowerLv() + 1 }
                }
            );
        }

        internal static void Add(string type, Dictionary<string, object> detail)
        {
            lock (Gate)
            {
                _seq++;
                Events.Add(
                    new TelemetryEvent
                    {
                        seq = _seq,
                        type = type,
                        game_time = Math.Round(UnityEngine.Time.time, 3),
                        detail = detail ?? new Dictionary<string, object>()
                    }
                );
                if (Events.Count > MaxEvents)
                {
                    Events.RemoveRange(0, Events.Count - MaxEvents);
                }
            }
        }

        internal static string EventsJson(long after)
        {
            lock (Gate)
            {
                return JsonMapper.ToJson(
                    new TelemetryEnvelope
                    {
                        latest_seq = _seq,
                        events = Events.FindAll(item => item.seq > after)
                    }
                );
            }
        }

        internal static TelemetrySummary Summary()
        {
            lock (Gate)
            {
                return new TelemetrySummary
                {
                    latest_seq = _seq,
                    enemy_damage = _enemyDamage,
                    hero_damage_taken = _heroDamage,
                    knight_damage_taken = _knightDamage,
                    enemy_kills = _kills,
                    leaks = _leaks,
                    tower_builds = _builds,
                    tower_upgrades = _upgrades,
                    tower_sales = _sales,
                    leaks_by_type = new Dictionary<string, int>(_leaksByType),
                    last_completed = _lastCompleted
                };
            }
        }
    }

}
