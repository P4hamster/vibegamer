using System;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace TowerMindPatcher
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            if (args.Length != 3)
            {
                Console.Error.WriteLine(
                    "usage: TowerMindPatcher <Assembly-CSharp.dll> <plugin.dll> <output.dll>"
                );
                return 2;
            }

            var source = Path.GetFullPath(args[0]);
            var pluginPath = Path.GetFullPath(args[1]);
            var output = Path.GetFullPath(args[2]);
            var resolver = new DefaultAssemblyResolver();
            resolver.AddSearchDirectory(Path.GetDirectoryName(source));
            resolver.AddSearchDirectory(Path.GetDirectoryName(pluginPath));

            using var plugin = AssemblyDefinition.ReadAssembly(
                pluginPath,
                new ReaderParameters { AssemblyResolver = resolver }
            );
            var bootstrap = plugin.MainModule.Types.Single(
                type => type.FullName == "SixAI.TowerMindPlugin.StandaloneBootstrap"
            );
            var install = bootstrap.Methods.Single(
                method => method.Name == "Install" && method.IsStatic
            );
            var refresh = bootstrap.Methods.Single(
                method => method.Name == "Refresh" && method.IsStatic
            );
            var telemetry = plugin.MainModule.Types.Single(
                type => type.FullName == "SixAI.TowerMindPlugin.TelemetryStore"
            );
            var episodeStarted = Method(telemetry, "EpisodeStarted");
            var damageFromAttack = Method(telemetry, "DamageFromAttack");
            var leak = Method(telemetry, "Leak");
            var actionConfirmed = Method(telemetry, "ActionConfirmed");
            var gameOver = Method(telemetry, "GameOver");

            using var game = AssemblyDefinition.ReadAssembly(
                source,
                new ReaderParameters
                {
                    AssemblyResolver = resolver,
                    InMemory = true,
                    ReadWrite = false
                }
            );
            var gameLoop = game.MainModule.Types.Single(type => type.Name == "GameLoop");
            var awake = gameLoop.Methods.Single(
                method => method.Name == "Awake" && method.Parameters.Count == 0
            );
            InsertBeforeReturns(
                awake,
                game.MainModule.ImportReference(install),
                loadThis: false
            );
            var onEpisodeBegin = Method(gameLoop, "OnEpisodeBegin");
            InsertAtStart(
                onEpisodeBegin,
                game.MainModule.ImportReference(episodeStarted),
                loadThis: false
            );
            InsertBeforeReturns(
                onEpisodeBegin,
                game.MainModule.ImportReference(refresh),
                loadThis: false
            );
            InsertAtStart(
                Method(game.MainModule.Types.Single(type => type.Name == "Character"), "ExecuteBeAttacked"),
                game.MainModule.ImportReference(damageFromAttack),
                loadThis: true,
                loadFirstArgument: true
            );
            InsertAtStart(
                Method(game.MainModule.Types.Single(type => type.Name == "Enemy"), "OnArrivalDest"),
                game.MainModule.ImportReference(leak),
                loadThis: true
            );
            InsertBeforeReturns(
                Method(gameLoop, "OnActionLanguageInfo"),
                game.MainModule.ImportReference(actionConfirmed),
                loadThis: true
            );
            InsertAtStart(
                Method(gameLoop, "OnGameOver"),
                game.MainModule.ImportReference(gameOver),
                loadThis: true
            );
            game.Write(output);
            Console.WriteLine(
                "patched bootstrap, reset refresh, and five telemetry callbacks: " + output
            );
            return 0;
        }

        private static MethodDefinition Method(TypeDefinition type, string name)
        {
            return type.Methods.Single(method => method.Name == name);
        }

        private static void InsertAtStart(
            MethodDefinition target,
            MethodReference callback,
            bool loadThis,
            bool loadFirstArgument = false
        )
        {
            var processor = target.Body.GetILProcessor();
            var first = target.Body.Instructions[0];
            if (loadThis)
            {
                processor.InsertBefore(first, processor.Create(OpCodes.Ldarg_0));
            }
            if (loadFirstArgument)
            {
                processor.InsertBefore(first, processor.Create(OpCodes.Ldarg_1));
            }
            processor.InsertBefore(first, processor.Create(OpCodes.Call, callback));
        }

        private static void InsertBeforeReturns(
            MethodDefinition target,
            MethodReference callback,
            bool loadThis
        )
        {
            var processor = target.Body.GetILProcessor();
            var returns = target.Body.Instructions
                .Where(instruction => instruction.OpCode == OpCodes.Ret)
                .ToList();
            foreach (var instruction in returns)
            {
                if (loadThis)
                {
                    processor.InsertBefore(instruction, processor.Create(OpCodes.Ldarg_0));
                }
                processor.InsertBefore(instruction, processor.Create(OpCodes.Call, callback));
            }
        }
    }
}
