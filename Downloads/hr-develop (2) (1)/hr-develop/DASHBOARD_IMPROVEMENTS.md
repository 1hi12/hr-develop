# 🎨 AMÉLIORATIONS DU DASHBOARD - Documentation

**Date:** 1 Mai 2026
**Fonctionnalités ajoutées:** Départements interactifs, Graphique interactif avec filtre Daily

---

## ✨ NOUVELLES FONCTIONNALITÉS

### 1. **Départements - Affichage des Job Postings** ✅

**Problème précédent:**
- Le widget "Departments" affichait "No department data available"
- Les données venaient de `CVFileModel` sans `job_id` associé

**Solution appliquée:**
- **Backend:** Utilisation des `JobPostingModel` actifs directement
- **Calcul des pourcentages:** Basé sur la distribution des offres actives par département
- **Données affichées:** Pourcentage + nombre d'offres par département

**Endpoint backend:**
```http
GET /api/v1/dashboard/departments
```

**Réponse:**
```json
[
  {
    "label": "Engineering",
    "value": 40,
    "count": 4
  },
  {
    "label": "Marketing",
    "value": 30,
    "count": 3
  },
  {
    "label": "Sales",
    "value": 30,
    "count": 3
  }
]
```

**Fichier modifié:** [app/api/v1/routes/dashboard.py](app/api/v1/routes/dashboard.py#L71-L102)

---

### 2. **Filtre "Daily" dans Applicant Trends** ✅

**Fonctionnalité:**
- Nouveau filtre "Daily" pour voir les candidats des **7 derniers jours**
- Groupement par jour pour une granularité fine

**Périodes disponibles:**
- **Daily** → 7 derniers jours (groupé par jour)
- **Last 1 Month** → 30 derniers jours (groupé par jour)
- **Last 3 Months** → 90 derniers jours (groupé par semaine)
- **Last 6 Months** → 180 derniers jours (groupé par mois)

**Backend support:**
```python
if period == "1d":
    # Last 7 days - daily grouping
    since = now - timedelta(days=7)
    trunc_unit = "day"
    fmt = "DD Mon"
```

**Frontend:**
```typescript
const periodMap: Record<string, '1d' | '1m' | '3m' | '6m'> = {
  'Daily': '1d',          // daily grouping (last 7 days)
  'Last 1 Month': '1m',   // daily grouping
  'Last 3 Months': '3m',  // weekly grouping
  'Last 6 Months': '6m',  // monthly grouping
}
```

---

### 3. **Graphique Interactif avec Modal** ✅

**Fonctionnalité principale:**
Cliquer sur un point du graphique "Applicant Trends" affiche une modal avec **tous les candidats** de cette période.

#### Comment ça fonctionne:

1. **Utilisateur clique sur un point** du graphique
2. **Frontend récupère la date/label** du point cliqué
3. **Appel API** vers `/api/v1/dashboard/trends/details?date={label}&period={period}`
4. **Backend retourne** tous les candidats créés pendant cette période
5. **Modal s'affiche** avec la liste complète des candidats

#### Endpoint backend:

```http
GET /api/v1/dashboard/trends/details?date=15%20Apr&period=1m
```

**Paramètres:**
- `date` (string): Label du point cliqué (ex: "15 Apr", "Apr 2026")
- `period` ('1d'|'1m'|'3m'|'6m'): Période sélectionnée (pour parser la date correctement)

**Réponse:**
```json
[
  {
    "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
    "full_name": "Jean Dupont",
    "email": "jean.dupont@email.com",
    "phone": "+33612345678",
    "location": "Paris, France",
    "status": "hired",
    "seniority_level": "senior",
    "total_years_experience": 8,
    "created_at": "2026-04-15T10:30:00Z"
  },
  {
    "candidate_id": "223e4567-e89b-12d3-a456-426614174001",
    "full_name": "Marie Martin",
    "email": "marie.martin@email.com",
    "phone": "+33698765432",
    "location": "Lyon, France",
    "status": "interviewing",
    "seniority_level": "junior",
    "total_years_experience": 3,
    "created_at": "2026-04-15T14:20:00Z"
  }
]
```

#### Logique de parsing des dates:

**Pour Daily/Last 1 Month (format: "DD Mon"):**
```python
parsed = datetime.strptime(f"{date} {now.year}", "%d %b %Y")
start_date = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
end_date = start_date + timedelta(days=1)
```

**Pour Last 3 Months (format: "DD Mon" - semaine):**
```python
parsed = datetime.strptime(f"{date} {now.year}", "%d %b %Y")
start_date = parsed - timedelta(days=parsed.weekday())  # Début de semaine
end_date = start_date + timedelta(days=7)
```

**Pour Last 6 Months (format: "Mon YYYY"):**
```python
parsed = datetime.strptime(date, "%b %Y")
start_date = parsed.replace(day=1, hour=0, minute=0, second=0)
# Calculate end of month
end_date = start_date.replace(month=parsed.month + 1) if parsed.month < 12 else start_date.replace(year=parsed.year + 1, month=1)
```

---

## 📊 INTERFACE UTILISATEUR

### Modal des candidats

**Design:**
- Header avec titre "Candidates for {date}" + compteur
- Bouton fermeture (X) en haut à droite
- Liste scrollable des candidats
- Chaque carte candidate affiche:
  - Avatar avec initiale
  - Nom complet
  - Seniority level
  - Email, téléphone, localisation
  - Années d'expérience
  - Badge de statut (colored)

**Statuts colorés:**
- **Hired** → Vert (bg-green-100 text-green-800)
- **Interviewing** → Bleu (bg-blue-100 text-blue-800)
- **Rejected** → Rouge (bg-red-100 text-red-800)
- **Pending** → Gris (bg-gray-100 text-gray-800)

**Responsive:**
- Modal s'adapte à la taille de l'écran
- Max-width: 4xl (896px)
- Max-height: 80vh
- Scroll interne pour listes longues

---

## 🔧 FICHIERS MODIFIÉS

### Backend

#### 1. **app/api/v1/routes/dashboard.py**

**Modifications:**

**Ligne 71-102:** Fonction `_fetch_departments()`
```python
async def _fetch_departments() -> list[dict]:
    """
    Hiring distribution by department (from active job postings) → [{label, value}] with percentages.
    Shows distribution of active job postings by department.
    """
    async with AsyncSessionLocal() as session:
        # Count active job postings by department
        result = await session.execute(
            select(
                JobPostingModel.department,
                func.count().label("count"),
            )
            .where(
                JobPostingModel.department.isnot(None),
                JobPostingModel.status == "active"  # Only active postings
            )
            .group_by(JobPostingModel.department)
        )
        rows = result.all()

    if not rows:
        return []

    total = sum(int(row.count) for row in rows)
    return [
        {
            "label": str(row.department),
            "value": round(int(row.count) / total * 100) if total > 0 else 0,
            "count": int(row.count),
        }
        for row in rows
    ]
```

**Ligne 105-147:** Fonction `_fetch_trends()` - Support '1d'
```python
async def _fetch_trends(period: Optional[str] = None) -> list[dict]:
    """
    CV uploads grouped by day/week/month depending on period.
    period: '1d' → daily (last 7 days), '1m' → daily, '3m' → weekly, '6m' or None → monthly
    """
    now = datetime.now(timezone.utc)

    if period == "1d":
        # Last 7 days - daily grouping
        since = now - timedelta(days=7)
        trunc_unit = "day"
        fmt = "DD Mon"
    elif period == "1m":
        # Last 30 days - daily grouping
        since = now - timedelta(days=30)
        trunc_unit = "day"
        fmt = "DD Mon"
    # ... etc
```

**Ligne 242-322:** Nouveau endpoint `get_trend_details()`
```python
@router.get("/trends/details")
async def get_trend_details(date: str, period: Optional[str] = None):
    """
    Get candidate details for a specific date/period in the trends chart.

    Args:
        date: Date label from the chart (e.g., "15 Apr", "Apr 2026")
        period: '1m' (daily), '3m' (weekly), '6m' (monthly)

    Response: [{candidate_id, full_name, email, created_at, status}]
    """
    # ... implementation
```

---

### Frontend

#### 1. **frontend/src/components/dashboard/ApplicantTrends.tsx**

**Modifications principales:**

**Imports ajoutés:**
```typescript
import { Tooltip, TooltipProps } from 'recharts'
import { X } from 'lucide-react'
```

**Nouveau state:**
```typescript
const [selectedDate, setSelectedDate] = useState<string | null>(null)
const [candidateDetails, setCandidateDetails] = useState<CandidateDetail[]>([])
const [loadingDetails, setLoadingDetails] = useState(false)
const [showModal, setShowModal] = useState(false)
```

**Fonction handleChartClick:**
```typescript
const handleChartClick = async (data: any) => {
  if (!data || !data.activeLabel) return

  const dateLabel = data.activeLabel
  setSelectedDate(dateLabel)
  setLoadingDetails(true)
  setShowModal(true)

  try {
    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const response = await fetch(
      `${API_BASE}/api/v1/dashboard/trends/details?date=${encodeURIComponent(dateLabel)}&period=${periodMap[period]}`
    )

    if (!response.ok) throw new Error('Failed to fetch candidate details')

    const details = await response.json()
    setCandidateDetails(details)
  } catch (error) {
    console.error('Error fetching candidate details:', error)
    setCandidateDetails([])
  } finally {
    setLoadingDetails(false)
  }
}
```

**Graphique modifié:**
```typescript
<LineChart
  data={chartData}
  margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
  onClick={handleChartClick}  // ← Ajouté
  style={{ cursor: 'pointer' }}  // ← Ajouté
>
  <Tooltip  // ← Ajouté
    contentStyle={{
      backgroundColor: '#1f2937',
      border: 'none',
      borderRadius: '8px',
      padding: '8px 12px',
      color: '#fff',
    }}
    cursor={{ stroke: '#5b5ce2', strokeWidth: 2, strokeDasharray: '5 5' }}
  />
  <Line
    type="natural"
    dataKey="value"
    stroke="#5b5ce2"
    strokeWidth={2.5}
    dot={{ fill: '#5b5ce2', r: 4, strokeWidth: 2, stroke: '#fff' }}  // ← Ajouté
    activeDot={{ r: 6, fill: '#5b5ce2', stroke: '#fff', strokeWidth: 2 }}  // ← Ajouté
    fill="url(#lineGradient)"
    animationDuration={300}
  />
</LineChart>
```

**Modal complète (lignes 201-295):**
- Header avec titre et compteur
- Bouton fermeture
- Loading state
- Empty state
- Liste scrollable des candidats avec toutes leurs infos

---

## 🎯 UTILISATION

### Voir les départements

1. Ouvrir http://localhost:5174/dashboard
2. Widget "Departments" affiche maintenant:
   - Distribution par département
   - Pourcentages calculés
   - Nombre d'offres actives par département

### Utiliser le filtre Daily

1. Aller sur le dashboard
2. Widget "Applicant Trends"
3. Cliquer sur le dropdown (en haut à droite)
4. Sélectionner "Daily"
5. Le graphique affiche les 7 derniers jours

### Voir les détails des candidats

1. Sur le graphique "Applicant Trends"
2. **Cliquer sur un point** de la courbe
3. Une modal s'ouvre avec:
   - Titre: "Candidates for {date}"
   - Nombre de candidats
   - Liste complète avec détails
4. Cliquer sur X ou hors de la modal pour fermer

---

## 📈 EXEMPLES D'UTILISATION

### Scénario 1: Analyser les candidatures journalières

```
1. Sélectionner "Daily" dans Applicant Trends
2. Voir les 7 derniers jours en détail
3. Cliquer sur le pic du 15 Apr
4. Modal montre: "5 candidates found"
5. Voir qui a postulé ce jour-là
6. Vérifier leur statut actuel
```

### Scénario 2: Analyser les départements qui recrutent

```
1. Regarder le widget "Departments"
2. Voir: Engineering 40%, Marketing 30%, Sales 30%
3. Savoir où concentrer les efforts de sourcing
4. Voir le nombre exact d'offres actives par département
```

### Scénario 3: Analyser une semaine spécifique

```
1. Sélectionner "Last 3 Months" (groupé par semaine)
2. Cliquer sur un point de la semaine du 8 Apr
3. Voir tous les candidats de cette semaine
4. Analyser les tendances de recrutement
```

---

## 🐛 GESTION DES ERREURS

### Backend

**Date invalide:**
```http
HTTP 400 Bad Request
{"detail": "Invalid date format"}
```

**Endpoint indisponible:**
```http
HTTP 500 Internal Server Error
{"detail": "Trend details unavailable"}
```

### Frontend

**Erreur réseau:**
- Modal s'affiche quand même
- Message: "Loading candidate details..."
- Puis: "No candidates found for this period"
- Console log de l'erreur

**Période sans candidats:**
- Modal s'affiche
- Message: "0 candidates found"
- Empty state: "No candidates found for this period"

---

## ✅ CHECKLIST DE TEST

### Départements

- [ ] Widget affiche les départements
- [ ] Pourcentages corrects (totalisent 100%)
- [ ] Nombre d'offres affiché
- [ ] Uniquement offres actives comptées
- [ ] Graphique donut coloré correctement

### Filtre Daily

- [ ] Option "Daily" visible dans le dropdown
- [ ] Sélection "Daily" charge les données
- [ ] Graphique affiche 7 derniers jours
- [ ] Labels des jours corrects (format "DD Mon")
- [ ] Données correctes pour chaque jour

### Graphique Interactif

- [ ] Curseur pointer au survol
- [ ] Tooltip s'affiche au survol
- [ ] Clic ouvre la modal
- [ ] Modal affiche le bon titre avec date
- [ ] Compteur de candidats correct
- [ ] Liste des candidats complète
- [ ] Détails candidats corrects (nom, email, status, etc.)
- [ ] Statuts colorés correctement
- [ ] Bouton X ferme la modal
- [ ] Clic hors modal ferme la modal
- [ ] Scroll fonctionne pour listes longues

---

## 🚀 PROCHAINES AMÉLIORATIONS POSSIBLES

1. **Filtre par statut dans la modal**
   - Filtrer les candidats par "hired", "interviewing", etc.

2. **Export CSV depuis la modal**
   - Bouton pour exporter la liste des candidats

3. **Lien vers la page candidat**
   - Cliquer sur un candidat → aller à sa page détail

4. **Graphique départements cliquable**
   - Cliquer sur un département → voir les offres

5. **Comparaison de périodes**
   - Voir évolution semaine N vs semaine N-1

6. **Filtres avancés**
   - Par seniority level
   - Par localisation
   - Par source de recrutement

---

## 📝 NOTES TECHNIQUES

### Performance

- **Lazy loading:** Modal charge les données uniquement au clic
- **Cache:** Données trend en cache (React Query)
- **Pagination:** Pas encore implémentée (à ajouter si >100 candidats/période)

### Sécurité

- **URL encoding:** Date encodée dans l'URL
- **Validation:** Backend valide le format de date
- **Error handling:** Try/catch complet frontend + backend

### Accessibilité

- **Keyboard:** Modal fermable avec Escape (à implémenter)
- **Screen readers:** Labels appropriés (à améliorer)
- **Focus trap:** À implémenter dans la modal

---

**Documentation mise à jour:** 1 Mai 2026
**Version:** 1.0
**Status:** ✅ Toutes les fonctionnalités implémentées et testables
