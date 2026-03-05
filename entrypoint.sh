#!/bin/sh
cp -rn /app/storage_defaults/. /app/app/storage/
exec "$@"