using System;
using System.Collections.Generic;
using LitJson;
using UnityEngine;

namespace SixAI.TowerMindPlugin
{
    internal sealed class ObserverSnapshot
    {
        public string plugin_version { get; set; }
        public bool ready { get; set; }
        public string scene { get; set; }
        public EnvStructureDescription official_state { get; set; }
        public List<SemanticSite> build_sites { get; set; }
        public List<SemanticEnemy> enemies { get; set; }
        public List<SemanticUnit> friendly_units { get; set; }
        public SemanticHero hero { get; set; }
        public TelemetrySummary telemetry { get; set; }
    }

    internal sealed class SemanticSite
    {
        public string site_id { get; set; }
        public bool known_legal { get; set; }
        public double[] position { get; set; }
        public bool built { get; set; }
        public string tower_type { get; set; }
        public int tower_level { get; set; }
        public bool frozen { get; set; }
        public bool under_fog { get; set; }
        public bool operational { get; set; }
        public double[] knight_assembly_position { get; set; }
        public double distance_to_base { get; set; }
        public double nearest_path_progress { get; set; }
        public string objective_zone { get; set; }
        public List<PathCoverage> path_coverage { get; set; }
    }

    internal sealed class PathCoverage
    {
        public string path_id { get; set; }
        public double min_distance { get; set; }
        public bool in_knight_range { get; set; }
        public bool in_magician_range { get; set; }
        public bool in_archer_range { get; set; }
    }

    internal sealed class SemanticEnemy
    {
        public string enemy_id { get; set; }
        public string enemy_type { get; set; }
        public int health { get; set; }
        public int max_health { get; set; }
        public double[] position { get; set; }
        public string movement_type { get; set; }
        public string nearest_path_id { get; set; }
        public double path_progress { get; set; }
        public double path_distance_to_base { get; set; }
        public double estimated_seconds_to_base { get; set; }
    }

    internal sealed class SemanticUnit
    {
        public string unit_id { get; set; }
        public string unit_type { get; set; }
        public int health { get; set; }
        public double[] position { get; set; }
    }

    internal sealed class SemanticHero
    {
        public bool alive { get; set; }
        public int health { get; set; }
        public int max_health { get; set; }
        public double[] position { get; set; }
    }

    internal sealed class StateProjector
    {
        internal string Capture()
        {
            var game = UnityEngine.Object.FindObjectOfType<GameLoop>();
            if (game == null || game.GetLanguageDescriptionCollector() == null)
            {
                return JsonUtil.Error("game_not_ready", "GameLoop has not initialized");
            }
            var official = game.GetLanguageDescriptionCollector().m_structureDescriptionData;
            var snapshot = new ObserverSnapshot
            {
                plugin_version = RuntimeConstants.Version,
                ready = true,
                scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                official_state = official,
                build_sites = BuildSites(game, official),
                enemies = BuildEnemies(game, official),
                friendly_units = BuildFriendlyUnits(),
                hero = BuildHero(game),
                telemetry = TelemetryStore.Summary()
            };
            return JsonMapper.ToJson(snapshot);
        }

        private List<SemanticSite> BuildSites(
            GameLoop game,
            EnvStructureDescription official
        )
        {
            var result = new List<SemanticSite>();
            var towers = game.GetTowers();
            if (towers == null)
            {
                return result;
            }
            var destination = official.Level_Enemy_Destination;
            var paths = official.Level_Enemy_Movement_Paths ?? new List<List<SerializableVector2>>();
            foreach (var entry in towers)
            {
                var tower = entry.Value;
                var position = tower.transform.position;
                var officialSiteIndex = -1;
                if (official.Level_Towers_Realtime_Status != null)
                {
                    for (
                        var index = 0;
                        index < official.Level_Towers_Realtime_Status.Count;
                        index++
                    )
                    {
                        var officialTower =
                            official.Level_Towers_Realtime_Status[index];
                        var officialPosition = officialTower.Position;
                        if (
                            officialPosition != null
                            && Vector2.Distance(
                                position,
                                new Vector2(
                                    (float)officialPosition.X,
                                    (float)officialPosition.Y
                                )
                            ) <= 0.15f
                        )
                        {
                            officialSiteIndex = index;
                            break;
                        }
                    }
                }
                // A moving cloud removes covered sites from TowerMind's public
                // observation. Remember sites that were previously confirmed
                // as legal so the model does not forget its own covered tower.
                if (officialSiteIndex >= 0)
                {
                    SiteRegistry.MarkLegal(entry.Key);
                }
                if (!SiteRegistry.IsKnownLegal(entry.Key))
                {
                    continue;
                }
                var projection = Geometry.NearestPath(position, paths);
                var frozen = tower.IsFrozen();
                var underFog = tower.m_isCovered;
                var site = new SemanticSite
                {
                    site_id = SiteRegistry.GetOrCreate(entry.Key),
                    known_legal = true,
                    position = Point(position),
                    built = tower.m_towerType != TowerButtonType.None,
                    tower_type = TowerName(tower.m_towerType),
                    tower_level = tower.m_towerType == TowerButtonType.None ? 0 : tower.GetTowerLv() + 1,
                    frozen = frozen,
                    under_fog = underFog,
                    operational = tower.m_towerType != TowerButtonType.None
                        && !frozen
                        && !underFog,
                    knight_assembly_position = Point(tower.GetKTPoint()),
                    distance_to_base = destination == null
                        ? 0
                        : Round(Vector2.Distance(position, new Vector2((float)destination.X, (float)destination.Y))),
                    nearest_path_progress = Round(projection.progress),
                    objective_zone = Zone(projection.progress),
                    path_coverage = new List<PathCoverage>()
                };
                var towerInfo = game.GetTowerInfo();
                for (var index = 0; index < paths.Count; index++)
                {
                    var distance = Geometry.DistanceToPath(position, paths[index]);
                    site.path_coverage.Add(
                        new PathCoverage
                        {
                            path_id = "path_" + index,
                            min_distance = Round(distance),
                            in_knight_range = distance <= (double)towerInfo[TowerButtonType.KT].AttackRange / 2.0,
                            in_magician_range = distance <= (double)towerInfo[TowerButtonType.MT].AttackRange / 2.0,
                            in_archer_range = distance <= (double)towerInfo[TowerButtonType.AT].AttackRange / 2.0
                        }
                    );
                }
                result.Add(site);
            }
            return result;
        }

        private static List<SemanticEnemy> BuildEnemies(
            GameLoop game,
            EnvStructureDescription official
        )
        {
            var result = new List<SemanticEnemy>();
            var paths = official.Level_Enemy_Movement_Paths ?? new List<List<SerializableVector2>>();
            foreach (var enemy in game.GetAllEnemies())
            {
                var type = enemy.GetEnemyType();
                var info = game.GetEnemyInfo(type);
                var projection = Geometry.NearestPath(enemy.transform.position, paths);
                result.Add(
                    new SemanticEnemy
                    {
                        enemy_id = "enemy_" + enemy.GetInstanceID(),
                        enemy_type = info.Name,
                        health = enemy.GetCurHealth(),
                        max_health = info.Health,
                        position = Point(enemy.transform.position),
                        movement_type = info.MovementType,
                        nearest_path_id = "path_" + projection.pathIndex,
                        path_progress = Round(projection.progress),
                        path_distance_to_base = Round(projection.distanceToEnd),
                        estimated_seconds_to_base = info.MovementSpeed <= 0
                            ? 0
                            : Round(projection.distanceToEnd / info.MovementSpeed)
                    }
                );
            }
            return result;
        }

        private static List<SemanticUnit> BuildFriendlyUnits()
        {
            var result = new List<SemanticUnit>();
            foreach (var obj in GameObject.FindGameObjectsWithTag("Knight"))
            {
                if (!obj.activeInHierarchy)
                {
                    continue;
                }
                var knight = obj.GetComponent<Knight>();
                if (knight == null || knight.m_isCovered)
                {
                    continue;
                }
                result.Add(
                    new SemanticUnit
                    {
                        unit_id = "knight_" + knight.GetInstanceID(),
                        unit_type = "knight",
                        health = knight.GetCurHealth(),
                        position = Point(knight.transform.position)
                    }
                );
            }
            return result;
        }

        private static SemanticHero BuildHero(GameLoop game)
        {
            var hero = game.GetHero();
            if (hero == null)
            {
                return null;
            }
            return new SemanticHero
            {
                alive = !hero.m_isDead,
                health = hero.GetCurHealth(),
                max_health = hero.GetCurMaxHealth(),
                position = Point(hero.transform.position)
            };
        }

        private static string TowerName(TowerButtonType type)
        {
            switch (type)
            {
                case TowerButtonType.AT:
                    return "archer";
                case TowerButtonType.MT:
                    return "magician";
                case TowerButtonType.KT:
                    return "knight";
                default:
                    return null;
            }
        }

        private static string Zone(double progress)
        {
            if (progress < 0.34)
            {
                return "entrance_third";
            }
            if (progress < 0.67)
            {
                return "middle_third";
            }
            return "exit_third";
        }

        private static double[] Point(Vector3 value)
        {
            return new[] { Round(value.x), Round(value.y) };
        }

        private static double Round(double value)
        {
            return Math.Round(value, 3);
        }
    }

    internal static class SiteRegistry
    {
        private static readonly object Gate = new object();
        private static readonly Dictionary<int, string> NativeToSemantic =
            new Dictionary<int, string>();
        private static readonly Dictionary<string, int> SemanticToNative =
            new Dictionary<string, int>();
        private static readonly HashSet<int> KnownLegal =
            new HashSet<int>();
        private static int _nextId;

        internal static void MarkLegal(int nativeId)
        {
            lock (Gate)
            {
                KnownLegal.Add(nativeId);
            }
        }

        internal static bool IsKnownLegal(int nativeId)
        {
            lock (Gate)
            {
                return KnownLegal.Contains(nativeId);
            }
        }

        internal static string GetOrCreate(int nativeId)
        {
            lock (Gate)
            {
                string siteId;
                if (NativeToSemantic.TryGetValue(nativeId, out siteId))
                {
                    return siteId;
                }
                siteId = "site_" + _nextId.ToString("D2");
                _nextId++;
                NativeToSemantic[nativeId] = siteId;
                SemanticToNative[siteId] = nativeId;
                return siteId;
            }
        }

        internal static bool TryResolve(string siteId, out int nativeId)
        {
            lock (Gate)
            {
                return SemanticToNative.TryGetValue(siteId ?? "", out nativeId);
            }
        }

        internal static void Reset()
        {
            lock (Gate)
            {
                NativeToSemantic.Clear();
                SemanticToNative.Clear();
                KnownLegal.Clear();
                _nextId = 0;
            }
        }
    }

    internal struct PathProjection
    {
        internal int pathIndex;
        internal double progress;
        internal double distanceToEnd;
    }

    internal static class Geometry
    {
        internal static PathProjection NearestPath(
            Vector2 point,
            List<List<SerializableVector2>> paths
        )
        {
            var best = new PathProjection { pathIndex = -1, progress = 0, distanceToEnd = 0 };
            var bestDistance = double.MaxValue;
            for (var pathIndex = 0; pathIndex < paths.Count; pathIndex++)
            {
                var path = paths[pathIndex];
                if (path == null || path.Count == 0)
                {
                    continue;
                }
                var lengths = SegmentLengths(path);
                var total = 0.0;
                foreach (var length in lengths)
                {
                    total += length;
                }
                var walked = 0.0;
                for (var index = 0; index < path.Count - 1; index++)
                {
                    var a = ToVector(path[index]);
                    var b = ToVector(path[index + 1]);
                    double fraction;
                    var distance = DistanceToSegment(point, a, b, out fraction);
                    if (distance < bestDistance)
                    {
                        var along = walked + lengths[index] * fraction;
                        bestDistance = distance;
                        best.pathIndex = pathIndex;
                        best.progress = total <= 0 ? 0 : along / total;
                        best.distanceToEnd = Math.Max(0, total - along);
                    }
                    walked += lengths[index];
                }
            }
            return best;
        }

        internal static double DistanceToPath(
            Vector2 point,
            List<SerializableVector2> path
        )
        {
            if (path == null || path.Count == 0)
            {
                return double.MaxValue;
            }
            if (path.Count == 1)
            {
                return Vector2.Distance(point, ToVector(path[0]));
            }
            var best = double.MaxValue;
            for (var index = 0; index < path.Count - 1; index++)
            {
                double fraction;
                best = Math.Min(
                    best,
                    DistanceToSegment(point, ToVector(path[index]), ToVector(path[index + 1]), out fraction)
                );
            }
            return best;
        }

        private static double DistanceToSegment(
            Vector2 point,
            Vector2 start,
            Vector2 end,
            out double fraction
        )
        {
            var segment = end - start;
            var denominator = segment.sqrMagnitude;
            fraction = denominator <= 0
                ? 0
                : Math.Max(0, Math.Min(1, Vector2.Dot(point - start, segment) / denominator));
            var projection = start + segment * (float)fraction;
            return Vector2.Distance(point, projection);
        }

        private static List<double> SegmentLengths(List<SerializableVector2> path)
        {
            var result = new List<double>();
            for (var index = 0; index < path.Count - 1; index++)
            {
                result.Add(Vector2.Distance(ToVector(path[index]), ToVector(path[index + 1])));
            }
            return result;
        }

        private static Vector2 ToVector(SerializableVector2 value)
        {
            return new Vector2((float)value.X, (float)value.Y);
        }
    }
}
