#!/bin/sh
cp -rn /app/storage_defaults/. /app/app/storage/
# Set SKIP_MIGRATIONS=1 where migrations run elsewhere (Railway's Pre-deploy Command), so a
# container that wakes from sleep doesn't import the app and hit the database just to find
# nothing to apply. Unset (local, docker run) it behaves as before.
if [ "$SKIP_MIGRATIONS" != "1" ]; then
    flask db upgrade
fi
exec "$@"
