# 🔧 CORRECTION CORS - Frontend/Backend Non Connectés

## ❌ PROBLÈME

Le frontend (port 5174) ne peut pas se connecter au backend (port 8000) à cause d'une erreur CORS:

```
Access to fetch at 'http://localhost:8000/api/v1/dashboard/stats'
from origin 'http://localhost:5174'
has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present
```

---

## ✅ SOLUTION APPLIQUÉE

**Fichier modifié:** `app/config/settings.py` (lignes 55-64)

**Changement:**
```python
# AVANT
cors_origins: list[str] = [
    "http://localhost:5173",  # Seulement port 5173
    ...
]

# APRÈS
cors_origins: list[str] = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",  # Vite dev server (port alternatif) ← AJOUTÉ
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",  # ← AJOUTÉ
    ...
]
```

---

## 🚀 ÉTAPES POUR APPLIQUER LA CORRECTION

### 1. **REDÉMARRER LE SERVEUR BACKEND**

**Important:** Les changements de configuration nécessitent un redémarrage!

```bash
# Dans le terminal du backend:
# 1. Arrêter le serveur (Ctrl+C)
# 2. Relancer:
uvicorn main:app --reload --port 8000
```

### 2. **RAFRAÎCHIR LE FRONTEND**

```bash
# Dans le navigateur:
# Appuyez sur F5 ou Ctrl+R
```

---

## ✅ VÉRIFICATION

Après le redémarrage, vous devriez voir dans la console:

### Backend:
```
INFO:     Application startup complete.
INFO:     127.0.0.1:xxxxx - "GET /api/v1/dashboard/stats HTTP/1.1" 200 OK
```

### Frontend (Console):
```
✅ Pas d'erreurs CORS
✅ Les données se chargent
```

---

## 🔍 DIAGNOSTIC

### Si le problème persiste:

1. **Vérifier le port du frontend:**
   ```
   Regardez l'URL dans le navigateur: http://localhost:XXXX
   ```

2. **Vérifier que le backend a redémarré:**
   ```bash
   # Le backend devrait afficher:
   INFO:     Application startup complete.
   ```

3. **Vérifier les logs du backend:**
   ```bash
   # Cherchez des erreurs dans le terminal du backend
   ```

4. **Tester l'API directement:**
   ```bash
   curl http://localhost:8000/api/v1/dashboard/stats
   # Devrait retourner du JSON
   ```

---

## 📝 PORTS AUTORISÉS

Le backend accepte maintenant les connexions de:

| Port | Description |
|------|-------------|
| 3000 | Create React App (dev) |
| 5173 | Vite dev server (default) |
| **5174** | **Vite dev server (alternatif)** ← VOTRE PORT |
| 8080 | Alternative dev server |

---

## 🎯 RÉSUMÉ

1. ✅ **Fichier modifié:** `app/config/settings.py`
2. ✅ **Port 5174 ajouté** aux origines CORS autorisées
3. 🔄 **Action requise:** Redémarrer le serveur backend
4. ✅ **Résultat:** Frontend et backend connectés

---

## 🚨 SI ÇA NE MARCHE TOUJOURS PAS

### Option 1: Utiliser le port 5173 (par défaut)

```bash
# Dans frontend/, arrêter le serveur et relancer:
npm run dev
# Vite choisira probablement le port 5173
```

### Option 2: Forcer le port 5173

```bash
# Dans frontend/package.json, modifier:
"scripts": {
  "dev": "vite --port 5173"
}

# Puis relancer:
npm run dev
```

### Option 3: Autoriser TOUS les ports (développement uniquement)

**⚠️ DANGER: N'utilisez JAMAIS en production!**

```python
# Dans app/config/settings.py:
cors_origins: list[str] = ["*"]  # Autorise TOUT
```

---

## ✅ CONFIRMATION

Après le redémarrage, votre dashboard devrait afficher:
- ✅ Statistiques des candidats
- ✅ Graphique des tendances
- ✅ Liste des départements
- ✅ Aucune erreur CORS dans la console

**Votre système est maintenant connecté!** 🎉
