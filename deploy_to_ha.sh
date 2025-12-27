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

# Clear ALL Python cache (including parent directories)
echo "🗑️  Clearing ALL Python cache..."
ssh ${HA_HOST} "sudo find /config/custom_components -name '*.pyc' -delete"
ssh ${HA_HOST} "sudo find /config/custom_components -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true"

# Restart Home Assistant
echo "🔄 Restarting Home Assistant..."
ssh ${HA_HOST} "bash -l -c 'ha core restart'"

echo "✅ Deployment complete!"
echo ""
echo "Waiting 40 seconds for HA to restart..."
sleep 40
echo ""
echo "📋 Tailing logs (Ctrl+C to stop)..."
echo "---"
ssh ${HA_HOST} "sudo docker logs -f homeassistant 2>&1 | grep veschub"
