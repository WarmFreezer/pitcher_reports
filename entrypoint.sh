#!/bin/sh
cp -rn /app/storage_defaults/. /app/app/storage/
flask db upgrade
flask migrate-school-storage
exec "$@"