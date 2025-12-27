# Version Management Workflow

## Releasing a New Version

Use the automated script to ensure version numbers stay in sync:

```bash
./tag_version.sh <version> "<description>"
```

**Example:**
```bash
./tag_version.sh 0.0.7 "Add CAN forwarding for multi-device BMS"
```

This will:
1. ✅ Update `manifest.json` version
2. ✅ Commit the version change  
3. ✅ Create git tag `v<version>`
4. ✅ Push commit and tag to GitHub

## Manual Process (Not Recommended)

If you need to do it manually:

```bash
# 1. Update manifest.json
sed -i 's/"version": ".*"/"version": "0.0.7"/' custom_components/veschub/manifest.json

# 2. Commit
git add custom_components/veschub/manifest.json
git commit -m "Bump version to 0.0.7"

# 3. Tag
git tag -a v0.0.7 -m "Description"

# 4. Push
git push && git push --tags
```

## Version Number Format

Use semantic versioning: `MAJOR.MINOR.PATCH`

- **0.0.x** - Prerelease/development
- **0.1.0** - First beta release
- **1.0.0** - First stable release

For now, we're in 0.0.x (prerelease) as we're still implementing core features.
