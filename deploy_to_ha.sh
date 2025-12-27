#!/bin/bash
# Fast deployment to Home Assistant over SSH
set -e

HA_HOST="hassio@192.168.1.10"
HA_PATH="/config/custom_components/veschub"
LOCAL_PATH="custom_components/veschub"

echo "📦 Deploying VESC Hub integration to HA..."

# Copy files to HA
echo "📤 Copying files..."
scp -r ${LOCAL_PATH}/*.py ${HA_HOST}:${HA_PATH}/
scp ${LOCAL_PATH}/manifest.json ${HA_HOST}:${HA_PATH}/

# Clear Python cache on remote
echo "🗑️  Clearing Python cache..."
ssh ${HA_HOST} "rm -rf ${HA_PATH}/__pycache__"

# Restart Home Assistant
echo "🔄 Restarting Home Assistant..."
ssh ${HA_HOST} "ha core restart"

echo "✅ Deployment complete!"
echo ""
echo "Waiting 30 seconds for HA to restart..."
sleep 30

echo "📋 Tailing logs (Ctrl+C to stop)..."
echo "---"
ssh ${HA_HOST} "tail -f /config/home-assistant.log | grep --line-buffered veschub"
