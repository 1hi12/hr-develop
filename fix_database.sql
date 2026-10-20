-- ============================================================
-- SQL POUR CORRIGER LA TABLE job_postings
-- ============================================================

-- Ajouter les colonnes manquantes à la table job_postings
ALTER TABLE job_postings
ADD COLUMN IF NOT EXISTS salary_min INTEGER,
ADD COLUMN IF NOT EXISTS salary_max INTEGER,
ADD COLUMN IF NOT EXISTS salary_currency VARCHAR(3) DEFAULT 'TND',
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE;

-- Mettre à jour la valeur par défaut pour les lignes existantes
UPDATE job_postings
SET salary_currency = 'TND'
WHERE salary_currency IS NULL;

-- Afficher la structure mise à jour
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'job_postings'
ORDER BY ordinal_position;
