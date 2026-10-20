import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def detect_language(text: str) -> str:
    """
    Détecte la langue d'un texte (français ou anglais).
    
    Args:
        text: Le texte à analyser
        
    Returns:
        'fr' pour français, 'en' pour anglais
    """
    text_lower = text.lower()
    
    # Mots clés français
    french_keywords = [
        'poste', 'candidat', 'compétences', 'expérience', 'formation', 'diplôme',
        'entreprise', 'équipe', 'développement', 'recherche', 'profil', 'mission',
        'responsabilités', 'qualifications', 'avantages', 'salaire', 'contrat',
        'stage', 'emploi', 'travail', 'société', 'bureau', 'service', 'département',
        'projet', 'gestion', 'analyse', 'conception', 'réalisation', 'maintenance',
        'être', 'avoir', 'faire', 'aller', 'dire', 'voir', 'savoir', 'pouvoir',
        'vouloir', 'venir', 'devoir', 'prendre', 'donner', 'mettre', 'passer',
        'français', 'anglais', 'maîtrise', 'niveau', 'langue', 'communication'
    ]
    
    # Mots clés anglais
    english_keywords = [
        'position', 'candidate', 'skills', 'experience', 'education', 'degree',
        'company', 'team', 'development', 'research', 'profile', 'mission',
        'responsibilities', 'qualifications', 'benefits', 'salary', 'contract',
        'internship', 'job', 'work', 'office', 'service', 'department',
        'project', 'management', 'analysis', 'design', 'implementation', 'maintenance',
        'the', 'and', 'you', 'will', 'have', 'with', 'for', 'this', 'that',
        'your', 'our', 'we', 'are', 'looking', 'seeking', 'required', 'preferred',
        'english', 'french', 'fluent', 'proficient', 'language', 'communication'
    ]
    
    # Compter les occurrences
    french_count = sum(1 for keyword in french_keywords if keyword in text_lower)
    english_count = sum(1 for keyword in english_keywords if keyword in text_lower)
    
    # Détection basée sur les caractères spéciaux français
    french_chars = (
        text.count('é') + text.count('è') + text.count('ê') + text.count('ë') +
        text.count('à') + text.count('â') + text.count('ù') + text.count('û') +
        text.count('ô') + text.count('ö') + text.count('î') + text.count('ï') +
        text.count('ç') + text.count('ÿ')
    )
    
    # Décision finale
    if french_chars > 0 or french_count > english_count:
        return 'fr'
    return 'en'

def get_localized_prompts(language: str) -> Dict[str, str]:
    """
    Retourne les prompts localisés selon la langue détectée.
    """
    if language == 'fr':
        return {
            'filter_prompt_prefix': """
Vous êtes un expert recruteur RH. Votre tâche est d'évaluer si un CV correspond à une offre d'emploi.

**Description du poste :**
{job_description}

**Résumé du CV :**
• Nom : {candidate_name}
• Contenu du CV : {cv_content}

**MISSION :**
Évaluez la pertinence de ce CV pour l'offre d'emploi. Considérez :
1. Adéquation du domaine (ex: développement web vs IA/ML vs backend)
2. Correspondance des compétences clés
3. Pertinence de l'expérience
4. Adéquation de la formation

**FORMAT DE RÉPONSE (JSON) :**
{{
    "relevance_score": [0.0-1.0],
    "domain_match": "[Excellent/Bon/Acceptable/Faible/Inadéquat]",
    "key_skills_match": "[Élevé/Moyen/Faible/Aucun]",
    "quick_assessment": "[Évaluation professionnelle sans scores techniques]",
    "proceed_to_detailed_analysis": [true/false],
    "decision": "[sélectionné/rejeté]"
}}
""",
            'explanation_prompt_prefix': """
Vous êtes un expert recruteur RH avec 15 ans d'expérience. Fournissez une évaluation professionnelle de la compatibilité de ce candidat avec l'offre d'emploi.

**Description du poste :**
{job_description}

**Profil du candidat :**
• Nom : {candidate_name}
• Email : {candidate_email}
• Téléphone : {candidate_phone}
• Statut : {status}

**Contenu du CV :**
{cv_content}

**MISSION :**
Fournissez une analyse structurée professionnelle suivant ce format :

**COMPATIBILITÉ GLOBALE :** [Excellente/Très bonne/Bonne/Moyenne/Faible]

**POINTS FORTS :**
• [Compétence technique spécifique qui correspond]
• [Expérience pertinente avec contexte]
• [Formation/certification alignée]

**POINTS À CONSIDÉRER :**
• [Lacunes importantes en compétences si applicable]
• [Évaluation du niveau d'expérience]
• [Besoins de formation supplémentaire si applicable]

**ANALYSE DÉTAILLÉE :**
• **Compétences techniques :** [Évaluation professionnelle]
• **Expérience :** [Pertinence pour le poste]
• **Secteur d'activité :** [Adéquation sectorielle]
• **Niveau du poste :** [Correspondance hiérarchique]

**RECOMMANDATION :**
[Recommandation professionnelle claire sans scores techniques]

**CONTRAINTES :**
- Soyez précis et professionnel
- Utilisez les termes exacts du CV et de l'offre d'emploi
- Justifiez chaque évaluation professionnellement
- Restez objectif et constructif
- Limitez la réponse à 200 mots maximum
- Concentrez-vous sur les qualifications, pas sur les scores techniques
""",
            'no_candidates_message': """📋 Résultats de Sélection des Candidatures
{separator}
Aucun candidat ne correspond actuellement aux critères du poste dans notre base de données.
Nous vous recommandons d'élargir vos critères de recherche ou de revoir certaines exigences.

📧 Notifications par email: {email_status}
📝 Intitulé du poste: {job_title}
""",
            'header_template': """🎯 Rapport de Sélection des Candidatures
{separator}
📝 Intitulé du poste: {job_title}
📊 Candidats sélectionnés: {selected_count}
📧 Notifications par email: {email_status}
🕐 Date d'analyse: {analysis_date}
""",
            'candidate_template': """---
🏆 Candidat {index} - SÉLECTIONNÉ:
👤 Nom: {name}
📧 Email: {email}
📞 Téléphone: {phone}
📋 Statut: {status}
{email_notification}
📝 Évaluation Professionnelle:
{explanation}
""",
            'summary_template': """📊 Résumé:
✅ Candidats sélectionnés: {selected_count}
{email_summary}
💡 Les notifications RH et candidats ont été envoyées automatiquement
📋 Seuls les candidats sélectionnés reçoivent des notifications par email
""",
            'email_sent': "✅ Email envoyé",
            'email_unavailable': "❌ Email non disponible",
            'email_error': "⚠️ Erreur d'envoi",
            'email_enabled': "Activées",
            'email_disabled': "Désactivées",
            'emails_sent_count': "📧 Emails envoyés: {sent}/{total}"
        }
    else:  # English
        return {
            'filter_prompt_prefix': """
You are an expert HR recruiter. Your task is to assess if a CV matches a job posting.

**Job Description:**
{job_description}

**CV Summary:**
• Name: {candidate_name}
• CV Content: {cv_content}

**TASK:**
Assess the relevance of this CV for the job posting. Consider:
1. Domain alignment (e.g., web dev vs AI/ML vs backend)
2. Core skill overlap
3. Experience relevance
4. Education alignment

**RESPONSE FORMAT (JSON):**
{{
    "relevance_score": [0.0-1.0],
    "domain_match": "[Excellent/Good/Fair/Poor/Mismatch]",
    "key_skills_match": "[High/Medium/Low/None]",
    "quick_assessment": "[Professional assessment without technical scores]",
    "proceed_to_detailed_analysis": [true/false],
    "decision": "[selected/rejected]"
}}
""",
            'explanation_prompt_prefix': """
You are an expert HR recruiter with 15 years of experience. Provide a professional assessment of this candidate's compatibility with the job posting.

**Job Description:**
{job_description}

**Candidate Profile:**
• Name: {candidate_name}
• Email: {candidate_email}
• Phone: {candidate_phone}
• Status: {status}

**CV Content:**
{cv_content}

**MISSION:**
Provide a professional structured analysis following this format :

**OVERALL COMPATIBILITY:** [Excellent/Very Good/Good/Average/Poor]

**STRENGTHS:**
• [Specific technical skill that matches]
• [Relevant experience with context]
• [Aligned education/certification]

**AREAS FOR CONSIDERATION:**
• [Important skill gaps if any]
• [Experience level assessment]
• [Additional training needs if applicable]

**DETAILED ANALYSIS:**
• **Technical Skills:** [Professional assessment]
• **Experience:** [Relevance to position]
• **Industry Background:** [Sector fit]
• **Position Level:** [Seniority match]

**RECOMMENDATION:**
[Clear professional recommendation without technical scores]

**CONSTRAINTS:**
- Be precise and professional
- Use exact terms from CV and job posting
- Justify each evaluation professionally
- Stay objective and constructive
- Limit response to 200 words maximum
- Focus on qualifications, not technical scoring
""",
            'no_candidates_message': """📋 Candidate Selection Results
{separator}
No candidates currently match the job criteria in our database.
We recommend broadening your search criteria or reviewing certain requirements.

📧 Email notifications: {email_status}
📝 Job title: {job_title}
""",
            'header_template': """🎯 Candidate Selection Report
{separator}
📝 Job title: {job_title}
📊 Selected candidates: {selected_count}
📧 Email notifications: {email_status}
🕐 Analysis date: {analysis_date}
""",
            'candidate_template': """---
🏆 Candidate {index} - SELECTED:
👤 Name: {name}
📧 Email: {email}
📞 Phone: {phone}
📋 Status: {status}
{email_notification}
📝 Professional Assessment:
{explanation}
""",
            'summary_template': """📊 Summary:
✅ Selected candidates: {selected_count}
{email_summary}
💡 HR and candidate notifications have been sent automatically
📋 Only selected candidates receive email notifications
""",
            'email_sent': "✅ Email sent",
            'email_unavailable': "❌ Email unavailable",
            'email_error': "⚠️ Send error",
            'email_enabled': "Enabled",
            'email_disabled': "Disabled",
            'emails_sent_count': "📧 Emails sent: {sent}/{total}"
        }

def get_localized_thinking_messages(language: str) -> Dict[str, str]:
    """
    Retourne les messages de thinking localisés.
    """
    if language == 'fr':
        return {
            'starting_filter': "🔍 Début du pré-filtrage LLM pour {count} CVs",
            'thinking_evaluating': "Réflexion... Évaluation du CV {cv_id} avec LLM pour la description du poste",
            'cv_selected': "✅ CV {cv_id} SÉLECTIONNÉ pour le poste",
            'cv_rejected': "❌ CV {cv_id} REJETÉ: {reason}",
            'separator': "=" * 60
        }
    else:  # English
        return {
            'starting_filter': "🔍 Starting LLM Pre-filtering for {count} CVs",
            'thinking_evaluating': "Thinking... Evaluating CV {cv_id} with LLM for job description",
            'cv_selected': "✅ CV {cv_id} SELECTED for position",
            'cv_rejected': "❌ CV {cv_id} REJECTED: {reason}",
            'separator': "=" * 60
        }

def get_localized_parse_response_fallback(language: str) -> Dict[str, Any]:
    """
    Retourne les valeurs de fallback pour le parsing des réponses.
    """
    if language == 'fr':
        return {
            'excellent_keywords': ['excellent', 'très pertinent', 'parfait'],
            'good_keywords': ['bon', 'pertinent', 'adéquat'],
            'fair_keywords': ['acceptable', 'convenable', 'moyen'],
            'poor_keywords': ['faible', 'inadéquat', 'mauvais'],
            'domain_match_unknown': 'Inconnu',
            'key_skills_unknown': 'Inconnu'
        }
    else:  # English
        return {
            'excellent_keywords': ['excellent', 'highly relevant', 'perfect'],
            'good_keywords': ['good', 'relevant', 'adequate'],
            'fair_keywords': ['fair', 'somewhat', 'average'],
            'poor_keywords': ['poor', 'mismatch', 'bad'],
            'domain_match_unknown': 'Unknown',
            'key_skills_unknown': 'Unknown'
        }
