# Steps 2-5 E2E Test Results — Enrichment: copyblogger.com

**Date:** 2026-03-28 13:35
**Prerequisite:** 145 posts from Step 1 crawl

---

## 2a. Embedding Analysis (Simulated)

| Metric | Value |
|--------|-------|
| Posts to embed | 145 |
| Total text chars | 1,667,937 |
| Estimated tokens | ~416,984 |
| Estimated cost | $0.0083 |
| Batches needed | 2 |
| Estimated time | 0.7s |
| Avg text length | 11,503 chars |
| Max text length | 20,000 chars |
| Texts hitting 20K truncation | 26 |

## 2b. Readability Scores

| Metric | Value |
|--------|-------|
| Posts scored | 145 |
| Processing time | 2.564s |
| **Avg Flesch Reading Ease** | **69.1** |
| **Avg Grade Level** | **7.3** |
| Min FRE | 30.2 |
| Max FRE | 81.2 |
| In sweet spot (60-80) | 133 (92%) |
| Too complex (<40) | 1 (1%) |

### Readability Distribution

| Range | Label | Count | % |
|-------|-------|-------|---|
| 90-100 | Very easy | 0 | 0% |
| 80-89 | Easy | 3 | 2% |
| 70-79 | Fairly easy | 67 | 46% |
| 60-69 | Standard | 57 | 39% |
| 50-59 | Fairly difficult | 7 | 5% |
| 30-49 | Difficult | 2 | 1% |
| 0-29 | Very confusing | 0 | 0% |

### Hardest to Read (Bottom 5)

| Title | FRE | Grade | Words |
|-------|-----|-------|-------|
| Copyblogger - Content marketing tools and training. | 30.2 | 12.7 | 186 |
| Copywriting 101: How to Craft Compelling Copy | 43.4 | 13.2 | 573 |
| How to Do Keyword Research: Steps, Examples, and Tools | 52.5 | 10.0 | 3,229 |
| Do You Spend $10,000 a Month on Pay Per Click Ads? | 53.3 | 10.0 | 546 |
| What Facebook Can Teach You About Effective Blog Market... | 56.9 | 9.7 | 1,924 |

## 2d. Intent Classification

| Intent | Count | % |
|--------|-------|---|
| informational | 140 | 96.6% |
| transactional | 2 | 1.4% |
| commercial | 2 | 1.4% |
| navigational | 1 | 0.7% |

### Non-Informational Posts

| Intent | Title | URL |
|--------|-------|-----|
| navigational | Everything You Need to Know About Writing Successf... | `/everything-you-need-to-know-about-writing-successfully` |
| transactional | Discover the Secret Mind Control Method That Hypno... | `/secret-mind-control-method` |
| commercial | Clever vs. Descriptive Headlines: Which Works Bett... | `/clever-vs-descriptive-headlines-which-works-better` |
| commercial | Top 10 Blogs for Writers 2007 | `/top-10-blogs-for-writers-2007` |
| transactional | Why I Won’t Buy Seth Godin’s Meatball Sundae | `/seth-godin-meatball-sundae` |

## 2e. AI Citability Scores

| Dimension | Avg | Min | Max |
|-----------|-----|-----|-----|
| Citability | 59.8 | 35 | 100 |
| E-E-A-T | 31.1 | 0 | 55 |
| Schema | 0.0 | 0.0 | 0.0 |
| Extraction | 65.3 | 35 | 95 |

**AI-ready posts (citability ≥ 60):** 73 (50.3%)
**Has schema:** 0 (0.0%)

### Most AI-Ready Posts (Top 5)

| Title | Citability | E-E-A-T | Schema | Extraction |
|-------|-----------|---------|--------|-----------|
| How to Do Keyword Research: Steps, Examples, and T... | 100 | 30 | 0.0 | 92 |
| How to Write Ebooks that Sell | 97 | 30 | 0.0 | 95 |
| How to Get 6,312 Subscribers to Your Business Blog... | 95 | 40 | 0.0 | 70 |
| The New Media Model for Creating Lifelong Customer... | 90 | 25 | 0.0 | 90 |
| Feel Great Naked: Confidence Boosters for Getting ... | 87 | 25 | 0.0 | 77 |

### Least AI-Ready Posts (Bottom 5)

| Title | Citability | E-E-A-T | Schema | Extraction |
|-------|-----------|---------|--------|-----------|
| Copyblogger - Content marketing tools and training... | 35 | 55 | 0.0 | 65 |
| The Art of the Joint Venture | 35 | 30 | 0.0 | 40 |
| How to Write for Google | 35 | 30 | 0.0 | 60 |
| How Copywriting Skills Can Improve Your Love Life | 35 | 30 | 0.0 | 35 |
| Telling People a Story They Want to Hear | 40 | 30 | 0.0 | 60 |

## AI Readiness Problems

**Total problems found:** 744

| Problem Type | Count | Severity Distribution |
|-------------|-------|----------------------|
| `missing_schema` | 145 | medium=145 |
| `geo_no_faq_section` | 145 | medium=145 |
| `geo_no_updated_date` | 145 | low=145 |
| `geo_low_data_density` | 131 | medium=131 |
| `weak_eeat` | 125 | medium=124, high=1 |
| `geo_no_question_headers` | 36 | medium=36 |
| `poor_ai_structure` | 7 | medium=7 |
| `geo_no_answer_first` | 6 | medium=6 |
| `low_ai_citability` | 4 | medium=4 |

## Sample Post Detail

**Title:** Is the New SEO Book Sales Letter Working?
**URL:** `https://copyblogger.com/is-the-new-seo-book-sales-letter-working`
**Citability:** 55/100
**E-E-A-T:** 30/100
**Schema:** 0.0/100
**Extraction:** 35/100

**Signals:**
```json
{
  "numbered_list_items": 3,
  "first_person_markers": 2,
  "definition_paragraphs": 7,
  "entity_density_per_1k": 21.4,
  "total_headers": 1,
  "answer_first_200w": true,
  "citability_score": 55,
  "eeat_author_found": true,
  "eeat_has_author_bio": true,
  "eeat_has_author_credentials": true,
  "eeat_eeat_score": 30,
  "extract_total_h2": 1,
  "extract_definition_count": 7,
  "extract_standalone_section_ratio": 1.0,
  "extract_total_list_items": 3,
  "extract_extraction_score": 35
}
```

## Processing Summary

| Step | Time | External API |
|------|------|-------------|
| Crawl (Step 1) | 81.3s | None |
| Embeddings (simulated) | ~0.7s | OpenAI $0.0083 |
| Readability | 2.564s | None |
| Intent | 0.009s | None |
| AI Citability | 9.813s | None |
| **Total Step 2** | **~13.1s** | **$0.0083** |
