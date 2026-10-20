# Sofrecom Logo

## Instructions

Pour que le logo Sofrecom apparaisse dans les emails de félicitations, veuillez :

1. Sauvegarder le logo Sofrecom (The Know-How Network) en format PNG
2. Nommer le fichier : **`sofrecom_logo.png`**
3. Placer le fichier dans ce répertoire

### Spécifications Recommandées

- **Format** : PNG (avec fond transparent) ou JPG
- **Dimensions** : 400x200 pixels ou similaire (ratio ~2:1)
- **Résolution** : 72-150 DPI pour email
- **Taille** : < 500 KB

### Emplacement Final

```
app/static/images/sofrecom_logo.png
```

### Vérification

Une fois le logo ajouté, testez l'email en visitant :
```
http://localhost:8000/api/v1/emails/preview-template
```

Le logo doit apparaître :
- Dans l'en-tête de l'email (grande version)
- Dans le pied de page (petite version)

---

**Note** : Si le logo n'est pas présent, les emails seront quand même envoyés, mais sans les images du logo.
