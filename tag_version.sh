#!/bin/bash
# Automated version tagging script
# Usage: ./tag_version.sh 0.0.7 "Description of changes"

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <version> <description>"
    echo "Example: $0 0.0.7 'Add CAN forwarding support'"
    exit 1
fi

VERSION=$1
DESCRIPTION=$2

echo "📦 Updating to version $VERSION"

# Update manifest.json version
echo "Updating manifest.json..."
sed -i "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" custom_components/veschub/manifest.json

# Commit the version change
git add custom_components/veschub/manifest.json
git commit -m "Bump version to $VERSION"

# Create and push tag
echo "Creating tag v$VERSION..."
git tag -a "v$VERSION" -m "$DESCRIPTION"

echo "Pushing to GitHub..."
git push
git push --tags

echo "✅ Version $VERSION released!"
echo ""
echo "Download URL:"
echo "https://github.com/radimklaska/ha_veschub/archive/refs/tags/v$VERSION.zip"
