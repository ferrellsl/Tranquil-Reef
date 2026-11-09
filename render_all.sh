#!/bin/sh
# Renders every fish (from its photo: swim + turn), the moray and the reef.  Run from the repo root.
#   sh render_all.sh [blender.exe]
# Needs photos/cut/*.png (python photos/prepare.py) and textures/ (python fetch_textures.py).
B=${1:-/c/Tools/blender-5.2.3-windows-x64/blender.exe}
set -e
# key  thickness  width-px  swim-amplitude  turn-frames (cruisers never turn)
cat > work/fishlist.txt <<'LIST'
yellowtang 0.16 340 0.070 20
bluetang   0.22 380 0.070 20
clown      0.35 280 0.075 20
angel      0.16 380 0.060 20
butterfly  0.16 330 0.065 20
queenangel 0.18 380 0.060 20
chromis    0.35 170 0.080 20
wrasse     0.45 380 0.080 20
barracuda  0.55 620 0.050 0
shark      0.50 760 0.060 0
LIST
while read key thick w amp turns; do
  echo "== $key"
  python photos/inflate.py "$key" "$thick"
  "$B" -b --factory-startup -P blender/photo3d.py -- "work/photo/$key.json" work/frames "$w" 12 64 "$turns" "$amp" > "work/log_$key.txt" 2>&1 || { echo "FAILED $key"; tail -20 "work/log_$key.txt"; }
  sleep 15   # let the GPU cool between species
done < work/fishlist.txt
echo "== moray"
python photos/moray_frames.py work/frames
if [ "$2" != "nofish-reef" ] && [ ! -f work/scene/scene_mask.png -o "$REEF" = "1" ]; then
  echo "== reef"
  "$B" -b --factory-startup -P blender/reef3d.py -- textures work/scene 384 > work/reef_log.txt 2>&1 || { echo "FAILED reef"; tail -20 work/reef_log.txt; }
fi
echo "== done"
# lionfish comes from a 3D model: blender/model3d.py -- scans/fish/lionfish.glb lionfish work/frames 400 12 64 20 0.04 y,z
# parrotfish, also a 3D model: blender/model3d.py -- scans/fish/parrotfish.glb parrotfish work/frames 380 12 64 20 0.06 x,z 1.7
# dark angelfish, a 3D model: blender/model3d.py -- scans/fish/coral_fish.glb darkangel work/frames 380 12 64 20 0.05 x,z 1.0
# copperband, a 3D model: blender/model3d.py -- scans/fish/small_fish.glb copperband work/frames 340 12 64 20 0.06 -x,z 1.0 whiten-blue
# puffer, a 3D model: blender/model3d.py -- scans/fish/sharpnose_puffer.glb puffer work/frames 300 12 64 20 0.035 x,z 1.5
