#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
runtime_dir="$project_dir/vendor/TowerMind/plugin_runtime/mac_apple_silicon/td.app/Contents/MacOS"
plugin_dir="$runtime_dir/BepInEx/plugins/TowerMind.Observer"
assembly="$project_dir/plugin/TowerMind.Observer/bin/Release/netstandard2.0/TowerMind.Observer.dll"
mechanics="$project_dir/plugin/generated/mechanics.json"
background="$project_dir/plugin/generated/hud_background.png"

if [ ! -f "$assembly" ]; then
    echo "Missing compiled plugin: $assembly" >&2
    exit 1
fi
if [ ! -f "$mechanics" ]; then
    echo "Missing generated mechanics: $mechanics" >&2
    exit 1
fi
if [ ! -f "$background" ]; then
    echo "Missing HUD background: $background" >&2
    exit 1
fi

mkdir -p "$plugin_dir"
cp "$assembly" "$plugin_dir/TowerMind.Observer.dll"
cp "$mechanics" "$plugin_dir/mechanics.json"
cp "$background" "$plugin_dir/hud_background.png"
chmod +x "$runtime_dir/run_bepinex.sh"
printf '%s\n' "$plugin_dir"
