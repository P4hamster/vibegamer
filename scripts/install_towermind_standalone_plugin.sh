#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
dotnet="$project_dir/.tools/dotnet/dotnet"
runtime="$project_dir/vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app"
managed="$runtime/Contents/Resources/Data/Managed"
streaming="$runtime/Contents/Resources/Data/StreamingAssets/TowerMind.Observer"
plugin="$project_dir/plugin/TowerMind.Observer/bin/Release/standalone/TowerMind.Observer.Standalone.dll"
background="$project_dir/plugin/generated/hud_background.png"
patcher="$project_dir/tools/TowerMindPatcher/bin/Release/net8.0/TowerMindPatcher.dll"
original="$managed/Assembly-CSharp.original.dll"
patched="/private/tmp/Assembly-CSharp.towermind-observer.patched.dll"

if [ ! -f "$plugin" ]; then
    echo "Missing standalone plugin: $plugin" >&2
    exit 1
fi

"$dotnet" build "$project_dir/tools/TowerMindPatcher/TowerMindPatcher.csproj" \
    -c Release \
    --nologo

if [ ! -f "$original" ]; then
    cp -p "$managed/Assembly-CSharp.dll" "$original"
fi

cp "$plugin" "$managed/TowerMind.Observer.Standalone.dll"
mkdir -p "$streaming"
cp "$project_dir/plugin/generated/mechanics.json" "$streaming/mechanics.json"
cp "$background" "$streaming/hud_background.png"

"$dotnet" "$patcher" "$original" "$plugin" "$patched"
cp "$patched" "$managed/Assembly-CSharp.dll"
printf '%s\n' "$runtime"
