# 🎯 EMAIL AUTOMATIQUE LORS DU RECRUTEMENT

## ✨ NOUVELLE FONCTIONNALITÉ

Lorsque vous changez le statut d'un candidat à **"hired"**, le système envoie **automatiquement** un email de félicitations professionnel au candidat!

---

## 🔧 COMMENT ÇA MARCHE?

### 1. **Changement de Statut via l'Interface**

Lorsque vous cliquez sur le bouton "Hired" dans la liste des candidats:

1. ✅ Le statut du candidat est mis à jour dans la base de données
2. ✅ Le système vérifie si le candidat a un email dans son CV
3. ✅ Un email professionnel avec le logo Sofrecom est envoyé automatiquement
4. ✅ Vous recevez une notification du résultat de l'envoi

---

## 📧 CAS D'UTILISATION

### Cas 1: Candidat avec Email ✅

```
Action: Cliquer sur "Hired" pour Jean Dupont
Résultat:
  ✅ Statut changé: pending → hired
  ✅ Email envoyé à: jean.dupont@email.com
  ✅ Notification: "Email de félicitations envoyé à jean.dupont@email.com"
```

### Cas 2: Candidat SANS Email ⚠️

```
Action: Cliquer sur "Hired" pour Candidat XYZ
Résultat:
  ✅ Statut changé: pending → hired
  ⚠️  Pas d'email trouvé dans le CV
  ⚠️  Notification: "Candidate XYZ has no email in their CV. Email notification skipped."
```

### Cas 3: Erreur d'Envoi ❌

```
Action: Cliquer sur "Hired" pour Marie Martin
Résultat:
  ✅ Statut changé: pending → hired
  ❌ Email non envoyé (problème SMTP)
  ❌ Notification: "Échec de l'envoi de l'email à marie.martin@email.com. Vérifiez la configuration SMTP."
```

---

## 🔍 D'OÙ VIENT L'EMAIL?

L'email du candidat est **extrait automatiquement du CV** lors de l'upload:

### Processus d'Extraction:

1. **Upload CV** → Le système lit le PDF/DOCX
2. **Extraction IA** → L'IA Gemini extrait les informations:
   - Nom complet
   - **Email** ← Important!
   - Téléphone
   - Compétences
   - Expériences
   - Etc.
3. **Stockage** → Les données sont sauvegardées dans `candidates.email`
4. **Utilisation** → Quand vous cliquez "Hired", cet email est utilisé

---

## 📊 API: Changer le Statut avec Job ID

### Requête HTTP:

```http
PATCH /api/v1/candidates/{candidate_id}/status
Content-Type: application/json

{
  "status": "hired",
  "job_id": "uuid-du-poste"  // Optionnel mais recommandé
}
```

### Avec `job_id` (Recommandé):

L'email contiendra les détails du poste:
- ✅ Titre du poste
- ✅ Département
- ✅ Localisation
- ✅ Type de contrat

```json
{
  "status": "hired",
  "job_id": "987fcdeb-51a2-43f1-b3c5-678901234567"
}
```

### Sans `job_id`:

L'email utilisera des valeurs par défaut:
- Titre: "Nouveau poste chez Sofrecom"
- Département: "À définir"
- Localisation: "Tunis, Tunisie"

```json
{
  "status": "hired"
}
```

---

## ✅ RÉPONSE API

### Succès avec Email Envoyé:

```json
{
  "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Jean Dupont",
  "email": "jean.dupont@email.com",
  "status": "hired",
  "email_sent": {
    "success": true,
    "message": "✅ Email de félicitations envoyé à jean.dupont@email.com",
    "email": "jean.dupont@email.com"
  },
  ...
}
```

### Succès SANS Email (CV sans email):

```json
{
  "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_name": "Candidat Sans Email",
  "email": null,
  "status": "hired",
  "email_sent": {
    "success": false,
    "message": "⚠️ Candidate Candidat Sans Email has no email in their CV. Email notification skipped.",
    "email": null
  },
  ...
}
```

---

## 🎨 CONTENU DE L'EMAIL

L'email contient:

### En-tête:
- ✅ Logo Sofrecom (si configuré)
- ✅ Titre: "Félicitations!"

### Corps:
- ✅ Message personnalisé avec le nom du candidat
- ✅ Détails du poste (titre, département, localisation, type de contrat)
- ✅ Prochaines étapes (contact RH, contrat, onboarding)
- ✅ Informations de contact RH

### Pied de page:
- ✅ Logo Sofrecom
- ✅ Signature "Sofrecom - The Know-How Network"
- ✅ Coordonnées

---

## 🔔 NOTIFICATIONS DANS L'INTERFACE

Le frontend peut afficher des notifications basées sur `email_sent`:

### Exemple React/TypeScript:

```typescript
async function updateCandidateStatus(candidateId: string, status: string, jobId?: string) {
  const response = await fetch(`/api/v1/candidates/${candidateId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, job_id: jobId })
  });

  const data = await response.json();

  // Afficher notification basée sur le résultat de l'email
  if (data.email_sent) {
    if (data.email_sent.success) {
      showNotification('success', data.email_sent.message);
      // "✅ Email de félicitations envoyé à jean.dupont@email.com"
    } else {
      showNotification('warning', data.email_sent.message);
      // "⚠️ Candidate XYZ has no email in their CV..."
    }
  }
}
```

---

## 🛡️ SÉCURITÉ ET VALIDATION

### Validations Automatiques:

1. ✅ **Vérification Email Existant**
   - Si `candidate.email` est `null` ou vide → email non envoyé
   - Notification d'avertissement retournée

2. ✅ **Éviter les Doublons**
   - Email envoyé SEULEMENT si le statut **change** de non-hired à hired
   - Si déjà "hired" et vous re-sauvegardez "hired" → pas d'email

3. ✅ **Gestion des Erreurs SMTP**
   - Si SMTP non configuré → log + notification
   - Si erreur réseau → retry automatique (dans email_service)
   - Résultat toujours retourné au frontend

---

## ⚙️ CONFIGURATION SMTP

Pour que les emails soient réellement envoyés:

### Dans `.env`:

```bash
# Configuration SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre.email@sofrecom.com
SMTP_PASSWORD=mot_de_passe_application

FROM_EMAIL=rh@sofrecom.com
FROM_NAME=Sofrecom RH
```

### Sans SMTP configuré:

- ✅ Le système fonctionne quand même
- ⚠️ Emails ne sont PAS envoyés (mode développement)
- ✅ Logs affichent le contenu de l'email
- ✅ Réponse API contient `success: false` avec message explicatif

---

## 📝 LOGS

### Succès:

```
INFO: [Candidates] Status updated: 123e4567 → hired (old: pending)
INFO: [HiredEmail] Email sent to jean.dupont@email.com (123e4567)
```

### Avertissement (pas d'email):

```
INFO: [Candidates] Status updated: 987fcdeb → hired (old: interviewing)
WARNING: [HiredEmail] No email for candidate 987fcdeb
```

### Erreur:

```
INFO: [Candidates] Status updated: 456e7890 → hired (old: pending)
ERROR: [HiredEmail] Failed to send email to marie@email.com
```

---

## 🎯 RÉSUMÉ

### Ce qui a été ajouté:

| Fonctionnalité | Statut |
|----------------|--------|
| Email automatique sur "hired" | ✅ |
| Validation email du candidat | ✅ |
| Notifications d'erreur | ✅ |
| Support job_id optionnel | ✅ |
| Éviter doublons d'emails | ✅ |
| Logs détaillés | ✅ |
| Fix DetachedInstanceError | ✅ |

### Workflow Complet:

```
1. Upload CV
   ↓
2. Extraction automatique (nom, email, skills...)
   ↓
3. Candidat ajouté avec email dans DB
   ↓
4. Vous cliquez "Hired"
   ↓
5. Statut updated → "hired"
   ↓
6. Système vérifie si email existe
   ↓
7a. Email existe → Email envoyé ✅
7b. Pas d'email → Notification ⚠️
   ↓
8. Frontend affiche résultat
```

---

## 🚀 PRÊT À UTILISER!

Le système est maintenant complètement fonctionnel:

```bash
# 1. Redémarrez le backend
uvicorn main:app --reload --port 8000

# 2. Testez en changeant un statut à "hired"
# 3. Vérifiez les logs pour confirmation
```

**Profitez de votre système d'emails automatiques!** 🎉
