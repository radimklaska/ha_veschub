#!/bin/bash
# Fast deployment to Home Assistant over SSH
set -e

HA_HOST="hassio@192.168.1.10"
HA_PATH="/config/custom_components/veschub"
LOCAL_PATH="custom_components/veschub"

echo "📦 Deploying VESC Hub integration to HA..."

# Copy files to HA using SSH stdin (HA doesn't have SCP)
echo "📤 Copying files..."
for file in ${LOCAL_PATH}/*.py ${LOCAL_PATH}/manifest.json; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        echo "  → $filename"
        cat "$file" | ssh ${HA_HOST} "sudo tee ${HA_PATH}/${filename} > /dev/null"
    fi
done

# Clear Python cache on remote
echo "🗑️  Clearing Python cache..."
ssh ${HA_HOST} "sudo rm -rf ${HA_PATH}/__pycache__"

# Restart HA - we'll restart integration instead of full HA restart
echo "✅ Files deployed!"
echo ""
echo "⚠️  Please restart the VESC Hub integration in HA UI:"
echo "   Settings → Devices & Services → VESC Hub → ⋮ → Reload"
echo ""
echo "Or restart Home Assistant manually if needed."
echo ""
echo "📋 Tailing logs (Ctrl+C to stop)..."
echo "---"
ssh ${HA_HOST} "tail -f /config/home-assistant.log | grep --line-buffered veschub"
