#!/bin/bash
# Dev server — hot-reload limité au dossier app/ pour éviter l'erreur mémoire WSL2
# (node_modules contient des centaines de milliers de fichiers qui saturent inotify)
set -e

uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir app \
  --reload-dir main.py
