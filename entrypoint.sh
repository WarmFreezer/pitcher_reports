#!/bin/sh
echo "Seeding volume..."

# For each file baked into the image, copy to volume if not already there
find /app/storage/defaults -type f | while read src; do
  # Replace /defaults/ with the actual storage path
  dest=$(echo "$src" | sed 's|/defaults||')
  if [ ! -f "$dest" ]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "Seeded: $dest"
  fi
done

echo "Seeding complete."
exec "$@"