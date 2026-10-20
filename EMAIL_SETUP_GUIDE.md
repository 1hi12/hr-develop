# Guide de Configuration des Emails - Sofrecom HR System

Ce guide explique comment configurer le système d'envoi d'emails professionnels pour les candidats recrutés.

## Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Configuration du Logo](#configuration-du-logo)
3. [Configuration SMTP](#configuration-smtp)
4. [Utilisation de l'API](#utilisation-de-lapi)
5. [Personnalisation des Templates](#personnalisation-des-templates)

---

## Vue d'ensemble

Le système d'envoi d'emails permet d'envoyer des emails professionnels de félicitations aux candidats recrutés, avec :

- **Design professionnel** avec le logo Sofrecom
- **Template HTML responsive** optimisé pour tous les appareils
- **Aucune mention des compétences/skills** du candidat
- **Informations du poste** (titre, département, localisation, etc.)
- **Branding Sofrecom** complet

### Architecture

```
app/
├── services/
│   └── email_service.py          # Service d'envoi d'emails
├── templates/
│   └── email/
│       └── hired_candidate.html  # Template HTML professionnel
├── static/
│   └── images/
│       └── sofrecom_logo.png     # Logo Sofrecom (à ajouter)
└── api/v1/routes/
    └── emails.py                 # Endpoints API
```

---

## Configuration du Logo

### Étape 1 : Ajouter le Logo Sofrecom

1. Sauvegardez le logo Sofrecom (l'image que vous avez fournie) sous le nom **`sofrecom_logo.png`**

2. Placez le fichier dans le répertoire :
   ```
   HR_System-main/app/static/images/sofrecom_logo.png
   ```

3. Le logo doit être :
   - Format : PNG (recommandé) ou JPG
   - Dimensions recommandées : 400x200 pixels ou similaire
   - Fond transparent (pour PNG)

### Étape 2 : Vérification

Le logo apparaîtra automatiquement dans :
- L'en-tête de l'email (grande version)
- Le pied de page (petite version)

Si le logo n'est pas trouvé, l'email sera quand même envoyé mais sans les images.

---

## Configuration SMTP

### Variables d'Environnement

Créez ou modifiez le fichier `.env` à la racine du projet :

```bash
# Configuration SMTP pour Gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre.email@sofrecom.com
SMTP_PASSWORD=votre_mot_de_passe_application

# Informations d'expéditeur
FROM_EMAIL=rh@sofrecom.com
FROM_NAME=Sofrecom RH
```

### Option 1 : Gmail (Recommandé pour les tests)

1. **Créer un mot de passe d'application** :
   - Allez sur https://myaccount.google.com/security
   - Activez la validation en 2 étapes
   - Allez dans "Mots de passe d'application"
   - Créez un nouveau mot de passe pour "Mail"
   - Copiez le mot de passe généré (16 caractères)

2. **Configuration dans `.env`** :
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=votre.email@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop  # Mot de passe d'application
   ```

### Option 2 : Serveur SMTP Sofrecom

Si Sofrecom dispose d'un serveur SMTP interne :

```bash
SMTP_HOST=smtp.sofrecom.com
SMTP_PORT=587  # ou 465 pour SSL
SMTP_USER=rh@sofrecom.com
SMTP_PASSWORD=mot_de_passe_rh
FROM_EMAIL=rh@sofrecom.com
FROM_NAME=Sofrecom Ressources Humaines
```

### Option 3 : Mode Développement (Sans SMTP)

Si les variables SMTP ne sont pas configurées, le système :
- Génère quand même le template HTML
- Enregistre les logs
- Retourne un succès (pour les tests)
- **Ne envoie PAS réellement l'email**

---

## Utilisation de l'API

### Endpoint 1 : Envoyer Email à un Candidat Recruté

**POST** `/api/v1/emails/send-hired-notification`

#### Request Body

```json
{
  "candidate_id": "uuid-du-candidat",
  "job_id": "uuid-du-poste",  // Optionnel
  "start_date": "15 Mai 2026"  // Optionnel
}
```

#### Exemple avec cURL

```bash
curl -X POST "http://localhost:8000/api/v1/emails/send-hired-notification" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
    "job_id": "987fcdeb-51a2-43f1-b3c5-678901234567",
    "start_date": "01 Juin 2026"
  }'
```

#### Exemple avec Python

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/emails/send-hired-notification",
    json={
        "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
        "job_id": "987fcdeb-51a2-43f1-b3c5-678901234567",
        "start_date": "01 Juin 2026"
    }
)

print(response.json())
```

#### Response Success

```json
{
  "status": "success",
  "message": "Email de félicitations envoyé à Jean Dupont",
  "recipient": "jean.dupont@email.com",
  "job_title": "Ingénieur Logiciel Senior",
  "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
  "job_id": "987fcdeb-51a2-43f1-b3c5-678901234567"
}
```

### Endpoint 2 : Envoyer Email de Test

**POST** `/api/v1/emails/send-test-email`

```bash
curl -X POST "http://localhost:8000/api/v1/emails/send-test-email" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_email": "votre.email@exemple.com"
  }'
```

### Endpoint 3 : Prévisualiser le Template

**GET** `/api/v1/emails/preview-template`

Ouvrez dans un navigateur :
```
http://localhost:8000/api/v1/emails/preview-template
```

Cela affiche le template HTML avec des données d'exemple.

---

## Personnalisation des Templates

### Modifier le Template Email

Le template est situé dans :
```
app/templates/email/hired_candidate.html
```

### Variables Disponibles

Vous pouvez utiliser ces variables Jinja2 dans le template :

| Variable | Description | Exemple |
|----------|-------------|---------|
| `{{candidate_name}}` | Nom complet du candidat | Jean Dupont |
| `{{job_title}}` | Titre du poste | Ingénieur Logiciel Senior |
| `{{department}}` | Département | Engineering |
| `{{location}}` | Localisation du poste | Tunis, Tunisie |
| `{{employment_type}}` | Type de contrat | CDI - Temps plein |
| `{{start_date}}` | Date de début | 01 Juin 2026 |
| `{{hr_email}}` | Email RH de contact | rh@sofrecom.com |
| `{{hr_phone}}` | Téléphone RH | +216 XX XXX XXX |

### Exemple de Personnalisation

Pour ajouter un message personnalisé, modifiez la section dans `hired_candidate.html` :

```html
<p class="message">
    Nous avons le plaisir de vous informer que votre candidature a été retenue
    pour le poste de <strong>{{job_title}}</strong> au sein de Sofrecom.
</p>

<!-- Ajoutez votre message personnalisé ici -->
<p class="message">
    Votre expertise en {{domain}} sera un atout majeur pour notre équipe.
</p>
```

---

## Intégration avec le Frontend

### Exemple React/TypeScript

```typescript
// Dans votre composant de gestion des candidats
async function sendHiredEmail(candidateId: string, jobId: string) {
  try {
    const response = await fetch('/api/v1/emails/send-hired-notification', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        candidate_id: candidateId,
        job_id: jobId,
        start_date: '15 Mai 2026'
      })
    });

    const data = await response.json();

    if (data.status === 'success') {
      alert(`Email envoyé avec succès à ${data.recipient}`);
    }
  } catch (error) {
    console.error('Erreur lors de l\'envoi de l\'email:', error);
  }
}
```

### Bouton dans l'UI

Ajoutez un bouton "Envoyer Email de Félicitations" dans votre interface de gestion des candidats :

```tsx
<button
  onClick={() => sendHiredEmail(candidate.id, job.id)}
  className="btn-primary"
>
  📧 Envoyer Email de Félicitations
</button>
```

---

## Dépannage

### L'email n'est pas envoyé

1. **Vérifiez les logs du serveur** :
   ```bash
   # Les logs affichent les erreurs SMTP
   tail -f logs/app.log
   ```

2. **Testez la configuration SMTP** :
   ```bash
   curl -X POST "http://localhost:8000/api/v1/emails/send-test-email" \
     -H "Content-Type: application/json" \
     -d '{"recipient_email": "votre.email@test.com"}'
   ```

3. **Vérifications communes** :
   - Les variables d'environnement SMTP sont bien définies
   - Le mot de passe d'application Gmail est correct (16 caractères)
   - Le firewall autorise la connexion au port 587
   - L'email du candidat existe dans la base de données

### Le logo ne s'affiche pas

1. Vérifiez que le fichier existe :
   ```bash
   ls -la HR_System-main/app/static/images/sofrecom_logo.png
   ```

2. Le logo doit être en PNG ou JPG

3. Testez avec le preview :
   ```
   http://localhost:8000/api/v1/emails/preview-template
   ```

---

## Support

Pour toute question ou problème :

1. Consultez les logs du serveur
2. Testez avec l'endpoint de prévisualisation
3. Vérifiez la documentation FastAPI : http://localhost:8000/docs

---

## Résumé des Étapes Rapides

1. ✅ **Ajouter le logo** : Sauvegardez `sofrecom_logo.png` dans `app/static/images/`
2. ✅ **Configurer SMTP** : Ajoutez les variables dans `.env`
3. ✅ **Tester** : Appelez `/api/v1/emails/send-test-email`
4. ✅ **Utiliser** : Appelez `/api/v1/emails/send-hired-notification` avec les IDs

Votre système d'envoi d'emails professionnels Sofrecom est maintenant prêt !
