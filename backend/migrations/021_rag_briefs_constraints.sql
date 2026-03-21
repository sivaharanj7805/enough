-- Migration 021: Relax CHECK constraints for RAG-enhanced recommendations + content briefs
-- The original CHECK constraints are too rigid for the expanding recommendation
-- and problem type vocabularies. Drop and re-add with broader values.

-- 1. Relax recommendation_type CHECK to allow new types
ALTER TABLE recommendations
    DROP CONSTRAINT IF EXISTS recommendations_recommendation_type_check;
ALTER TABLE recommendations
    ADD CONSTRAINT recommendations_recommendation_type_check
    CHECK (recommendation_type IN (
        'merge', 'refresh', 'optimize', 'delete', 'expand', 'interlink', 'growth',
        'differentiate', 'redirect',
        'add_schema', 'improve_ai_citability', 'strengthen_eeat', 'improve_ai_structure'
    ));

-- 2. Relax content_problems problem_type CHECK to allow AI-era types
ALTER TABLE content_problems
    DROP CONSTRAINT IF EXISTS content_problems_problem_type_check;
ALTER TABLE content_problems
    ADD CONSTRAINT content_problems_problem_type_check
    CHECK (problem_type IN (
        'decay_mild', 'decay_moderate', 'decay_severe',
        'thin_content', 'thin_below_cluster_avg', 'thin_high_bounce',
        'seo_missing_meta', 'seo_title_length', 'seo_no_headings',
        'seo_no_internal_links', 'seo_no_images',
        'orphan', 'cannibalization',
        'readability_too_complex',
        'low_ai_citability', 'weak_eeat', 'missing_schema', 'poor_ai_structure'
    ));

-- 3. Add confidence column to recommendations if not present
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS confidence TEXT;

-- 4. Add cannibalization_risk + differentiation_notes to content_briefs
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS cannibalization_risk TEXT;
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS differentiation_notes TEXT;
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS avoid_topics TEXT[] DEFAULT '{}';
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS internal_links_from JSONB DEFAULT '[]';
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS internal_links_to JSONB DEFAULT '[]';
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS content_angle TEXT;
ALTER TABLE content_briefs ADD COLUMN IF NOT EXISTS difficulty_level TEXT;
