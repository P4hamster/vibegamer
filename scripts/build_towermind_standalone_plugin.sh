#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
dotnet="$project_dir/.tools/dotnet/dotnet"
compiler="$project_dir/.tools/dotnet/sdk/8.0.423/Roslyn/bincore/csc.dll"
runtime="$project_dir/vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app"
managed="$runtime/Contents/Resources/Data/Managed"
source_dir="$project_dir/plugin/TowerMind.Observer"
output_dir="$source_dir/bin/Release/standalone"

mkdir -p "$output_dir"
"$dotnet" "$compiler" \
    -noconfig \
    -nostdlib+ \
    -target:library \
    -langversion:latest \
    -deterministic+ \
    -optimize+ \
    -out:"$output_dir/TowerMind.Observer.Standalone.dll" \
    -r:"$managed/mscorlib.dll" \
    -r:"$managed/System.dll" \
    -r:"$managed/System.Core.dll" \
    -r:"$managed/System.Runtime.dll" \
    -r:"$managed/netstandard.dll" \
    -r:"$managed/Assembly-CSharp.dll" \
    -r:"$managed/LitJson.dll" \
    -r:"$managed/Unity.ML-Agents.dll" \
    -r:"$managed/UnityEngine.dll" \
    -r:"$managed/UnityEngine.CoreModule.dll" \
    -r:"$managed/UnityEngine.ImageConversionModule.dll" \
    -r:"$managed/UnityEngine.IMGUIModule.dll" \
    -r:"$managed/UnityEngine.JSONSerializeModule.dll" \
    -r:"$managed/UnityEngine.Physics2DModule.dll" \
    -r:"$managed/UnityEngine.TextRenderingModule.dll" \
    -r:"$managed/Unity.TextMeshPro.dll" \
    "$source_dir/BridgeServer.cs" \
    "$source_dir/CommandExecutor.cs" \
    "$source_dir/RuntimeSupport.cs" \
    "$source_dir/StandaloneBootstrap.cs" \
    "$source_dir/StateProjector.cs" \
    "$source_dir/Telemetry.cs"

printf '%s\n' "$output_dir/TowerMind.Observer.Standalone.dll"
