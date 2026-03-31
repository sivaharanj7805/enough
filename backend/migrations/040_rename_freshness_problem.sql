-- Rename geo_no_freshness_date → geo_no_updated_date for clarity.
-- The problem checks for visible "last modified" signals, not publish dates.
-- The old name was misleading when 99% of posts have publish_date but still
-- triggered this problem because they lack a MODIFIED/UPDATED signal.

-- Drop old constraint FIRST so the UPDATE doesn't violate it
ALTER TABLE content_problems DROP CONSTRAINT IF EXISTS content_problems_problem_type_check;

UPDATE content_problems SET problem_type = 'geo_no_updated_date'
WHERE problem_type = 'geo_no_freshness_date';
ALTER TABLE content_problems ADD CONSTRAINT content_problems_problem_type_check
    CHECK (problem_type IN (
        'thin_content', 'thin_below_cluster_avg', 'content_decay', 'high_bounce', 'orphan',
        'seo_missing_meta', 'seo_title_length', 'seo_no_headings',
        'seo_no_outbound_links', 'seo_no_images', 'seo_no_internal_links',
        'ranking_slip', 'readability_too_complex',
        'low_ai_citability', 'weak_eeat', 'missing_schema', 'poor_ai_structure',
        'geo_no_faq_section', 'geo_no_question_headers', 'geo_low_data_density',
        'geo_no_answer_first', 'geo_missing_faq_schema', 'geo_no_updated_date',
        'velocity_decline', 'intent_mismatch', 'serp_opportunity_missed'
    ));
