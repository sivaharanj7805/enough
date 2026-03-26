-- Migration 037: Relax CHECK constraints for GEO problem types and recommendation types.
-- The original CHECK constraints in migration 021 didn't include the new GEO-specific
-- problem types and recommendation types added in the GEO roadmap (GEO-3, GEO-8).

-- 1. Relax content_problems problem_type CHECK
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
        'low_ai_citability', 'weak_eeat', 'missing_schema', 'poor_ai_structure',
        'geo_no_faq_section', 'geo_no_data_tables', 'geo_no_experience_markers',
        'geo_no_question_headers', 'geo_low_data_density', 'geo_no_answer_first',
        'geo_missing_faq_schema', 'geo_no_freshness_date',
        'velocity_decline', 'intent_mismatch', 'serp_opportunity_missed'
    ));

-- 2. Relax recommendations recommendation_type CHECK
ALTER TABLE recommendations
    DROP CONSTRAINT IF EXISTS recommendations_recommendation_type_check;
ALTER TABLE recommendations
    ADD CONSTRAINT recommendations_recommendation_type_check
    CHECK (recommendation_type IN (
        'merge', 'refresh', 'optimize', 'delete', 'expand', 'interlink', 'growth',
        'differentiate', 'redirect', 'update',
        'add_schema', 'improve_ai_citability', 'strengthen_eeat', 'improve_ai_structure',
        'add_faq_section', 'reformat_headers_geo', 'increase_data_density',
        'add_answer_first', 'add_faq_schema', 'add_freshness_signal'
    ));
