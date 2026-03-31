# Step 6b E2E Test Results: copyblogger.com

**Date:** 2026-03-28 20:08
**Prerequisite:** 145 posts from Step 1 crawl + Step 3 clustering (synthetic embeddings)
**Clusters labeled:** 4
**Note:** Clustering used synthetic embeddings (not real OpenAI). Cluster composition differs from production; label quality assessment is valid for the TF-IDF algorithm but cluster boundaries are artificial.

---

## 6b-a. Site-Wide Stop Word Detection

| Metric | Value |
|--------|-------|
| Total titles analyzed | 145 |
| Stop word threshold | 29 occurrences (20% of 145 titles) |
| Site stops detected | 0 |
| Stop words | (none) |
| Processing time | 5.05ms |

### Word Frequency Analysis (Top 20)

| Word | Titles Containing | % | Stopped? |
|------|------------------|---|----------|
| blog | 11/145 | 8% |  |
| content | 10/145 | 7% |  |
| copy | 9/145 | 6% |  |
| marketing | 7/145 | 5% |  |
| writing | 7/145 | 5% |  |
| blogging | 6/145 | 4% |  |
| story | 6/145 | 4% |  |
| headlines | 6/145 | 4% |  |
| copywriting | 6/145 | 4% |  |
| bloggers | 5/145 | 3% |  |
| people | 5/145 | 3% |  |
| business | 5/145 | 3% |  |
| media | 5/145 | 3% |  |
| copyblogger | 4/145 | 3% |  |
| seo | 4/145 | 3% |  |
| words | 4/145 | 3% |  |
| click | 3/145 | 2% |  |
| page | 3/145 | 2% |  |
| landing | 3/145 | 2% |  |
| become | 3/145 | 2% |  |

## 6b-b. Format Marker Stripping

| Metric | Value |
|--------|-------|
| Titles modified | 19/145 (13.1%) |
| Format markers checked | 16 patterns |
| Leading patterns stripped | `How to`, `What Is`, `N Best/Top...` |
| Trailing patterns stripped | Year (`in 2024`), site name (`- Copyblogger`) |

### Stripping Examples

| Original Title | After Stripping |
|---------------|----------------|
| Everything You Need to Know About Writing Successfully | about writing successfully |
| How to Get on Techmeme in 3 Simple Steps | get on techmeme in 3 simple steps |
| How to Write for Google | write for google |
| There’s Never Been a Better Time to Be a Business-Savvy Writer | there’s never been a better time to be a business |
| How to Be a Conversational Blogger Who People Listen To | be a conversational blogger who people listen to |
| How to Use the Simple Power of Contrast to Become More Persuasive | use the simple power of contrast to become more persuasive |
| Once More With Feeling: Has Your Writing Got Soul? | once more with feeling |
| How to be a Rock Star in Your Niche | be a rock star in your niche |
| How to Become a Heroic Business Blogger | become a heroic business blogger |
| How to Get 6,312 Subscribers to Your Business Blog in One Day | get 6,312 subscribers to your business blog in one day |
| How to Write Remarkably Creative Content | write remarkably creative content |
| What is a Copywriter's Most Valuable Trait? | a copywriter's most valuable trait? |
| How to Write Ebooks that Sell | write ebooks that sell |
| Clever vs. Descriptive Headlines: Which Works Better? | clever vs. descriptive headlines |
| How to Create a Blog That People Really Digg | create a blog that people really digg |

## 6b-c. Phrase Extraction

| Metric | Value |
|--------|-------|
| Total unigrams extracted | 557 |
| Total bigrams extracted | 412 |
| Unique unigrams | 378 |
| Unique bigrams | 399 |
| Phrases per title (mean) | 6.7 |
| Phrases per title (median) | 7.0 |
| Phrases per title (range) | 1-19 |

### Top 15 Unigrams (Corpus-Wide)

| Unigram | Frequency | In Site Stops? |
|---------|-----------|---------------|
| blog | 11 |  |
| content | 10 |  |
| copy | 9 |  |
| marketing | 7 |  |
| writing | 7 |  |
| blogging | 6 |  |
| story | 6 |  |
| headlines | 6 |  |
| copywriting | 6 |  |
| bloggers | 5 |  |
| people | 5 |  |
| business | 5 |  |
| media | 5 |  |
| copyblogger | 4 |  |
| seo | 4 |  |

### Top 15 Bigrams (Corpus-Wide)

| Bigram | Frequency |
|--------|-----------|
| landing page | 3 |
| social media | 3 |
| content promotion | 3 |
| pay per | 2 |
| per click | 2 |
| sales letter | 2 |
| seo book | 2 |
| blog post | 2 |
| thanks google | 2 |
| strategic content | 2 |
| copyblogger content | 1 |
| content marketing | 1 |
| marketing tools | 1 |
| tools training | 1 |
| steps pay | 1 |

## Multi-Signal Phrase Diagnostic

| Source | Total Phrases | Notes |
|--------|--------------|-------|
| Titles (3x weight) | 969 | Extracted via `_extract_phrases` |
| Body text (1x weight) | 2175 | First 200 words of `body_html` |
| H2/H3 headings (2x weight) | 1047 | From `headings` JSONB |
| **Total input to TF-IDF** | **7176** | **Weighted sum** |

## 6b-d. Per-Cluster TF-IDF Labeling

### Cluster 1 (53 posts) -> "Content Promotion & Writing"

| Metric | Value |
|--------|-------|
| Label | **Content Promotion & Writing** |
| Description | Posts covering blogging and copywriting. |
| Posts | 53 |
| Title phrases | 355 |
| Body phrases | 795 |
| Heading phrases | 544 |
| Unique bigrams | 147 |
| Unique unigrams | 149 |
| Specific (validation) | YES |
| Label bigram source | title=3, body=1, heading=0 |
| Alternatives | Content Marketing, Content & Writing, Writing & Blogging |
| Description words | Blogging, Copywriting |
| Labeling time | 7.5ms |

**Top 5 Bigrams by TF-IDF:**

| Bigram | TF-IDF Score | Frequency | Selected? |
|--------|-------------|-----------|----------|
| content promotion | 0.0713 | 3 | YES |
| blog post | 0.0514 | 2 |  |
| strategic content | 0.0514 | 2 |  |
| copyblogger content | 0.0284 | 1 |  |
| content marketing | 0.0284 | 1 |  |

**Top 5 Unigrams by TF-IDF:**

| Unigram | TF-IDF Score |
|---------|-------------|
| content | 0.1264 |
| blogging | 0.0891 |
| headlines | 0.0891 |
| copywriting | 0.0891 |
| blog | 0.0855 |

**Sample titles (first 8):**

- Copyblogger - Content marketing tools and training.
- Why the AdWords Landing Page Fiasco Won’t Hurt Bloggers
- The True Power of the Blog
- Why “Content” Has Become a Dirty Word
- The Most Powerful Blogging Technique There Is
- Aristotle’s Top 3 Tips for Effective Blogging
- Blogging Grows Up
- Why Magnetic Headlines Attract More Readers

### Cluster 3 (44 posts) -> "Social Media & People"

| Metric | Value |
|--------|-------|
| Label | **Social Media & People** |
| Description | Posts covering marketing. |
| Posts | 44 |
| Title phrases | 322 |
| Body phrases | 660 |
| Heading phrases | 228 |
| Unique bigrams | 135 |
| Unique unigrams | 158 |
| Specific (validation) | YES |
| Label bigram source | title=3, body=7, heading=1 |
| Alternatives | Copywriter Curse, People & Media, Media & Marketing |
| Description words | Marketing |
| Labeling time | 5.2ms |

**Top 5 Bigrams by TF-IDF:**

| Bigram | TF-IDF Score | Frequency | Selected? |
|--------|-------------|-----------|----------|
| social media | 0.0775 | 3 | YES |
| pay per | 0.0558 | 2 |  |
| per click | 0.0558 | 2 |  |
| steps pay | 0.0308 | 1 |  |
| click advertising | 0.0308 | 1 |  |

**Top 5 Unigrams by TF-IDF:**

| Unigram | TF-IDF Score |
|---------|-------------|
| media | 0.0870 |
| marketing | 0.0792 |
| social | 0.0589 |
| story | 0.0497 |
| copy | 0.0438 |

**Sample titles (first 8):**

- 5 Steps to Pay Per Click Advertising That Works
- It’s the End of AdSense as We Know It (And I Feel Fine)
- Titles That Tell a Whole Story
- Telling People a Story They Want to Hear
- Is Net Neutrality Down for the Count?
- Discover the Secret Mind Control Method That Hypnotically Persuades Prospects to
- Does Your Copy Look Spammy?
- News Flash

### Cluster 0 (24 posts) -> "Business Blog & People"

| Metric | Value |
|--------|-------|
| Label | **Business Blog & People** |
| Description | Posts covering story. |
| Posts | 24 |
| Title phrases | 134 |
| Body phrases | 360 |
| Heading phrases | 63 |
| Unique bigrams | 55 |
| Unique unigrams | 66 |
| Specific (validation) | YES |
| Label bigram source | title=1, body=1, heading=0 |
| Alternatives | Blog & Business, Business & People, People & Naked |
| Description words | Story |
| Labeling time | 3.0ms |

**Top 5 Bigrams by TF-IDF:**

| Bigram | TF-IDF Score | Frequency | Selected? |
|--------|-------------|-----------|----------|
| words business | 0.0779 | 1 |  |
| business bloggers | 0.0779 | 1 |  |
| techmeme steps | 0.0779 | 1 |  |
| call tonight | 0.0779 | 1 |  |
| tonight question | 0.0779 | 1 |  |

**Top 5 Unigrams by TF-IDF:**

| Unigram | TF-IDF Score |
|---------|-------------|
| business | 0.1613 |
| people | 0.1209 |
| create | 0.0982 |
| blogger | 0.0982 |
| killer | 0.0982 |

**Sample titles (first 8):**

- For Whom the Blog Tips (It Tips For Thee)
- What’s Your Story?
- The 9 Most Important Words for Business Bloggers
- How to Get on Techmeme in 3 Simple Steps
- Why People Want to Know What’s In It For *You*
- Call Me Tonight if You Have a Question
- Five Reasons Why the List Post is Dead
- The Smart Way to Create a Sense of Urgency

### Cluster 2 (24 posts) -> "Landing Page & Keyword"

| Metric | Value |
|--------|-------|
| Label | **Landing Page & Keyword** |
| Description | Posts covering seo and google. |
| Posts | 24 |
| Title phrases | 158 |
| Body phrases | 360 |
| Heading phrases | 212 |
| Unique bigrams | 64 |
| Unique unigrams | 78 |
| Specific (validation) | YES |
| Label bigram source | title=2, body=2, heading=0 |
| Alternatives | Keyword & SEO, SEO & Research, Research & Google |
| Description words | SEO, Google |
| Labeling time | 4.5ms |

**Top 5 Bigrams by TF-IDF:**

| Bigram | TF-IDF Score | Frequency | Selected? |
|--------|-------------|-----------|----------|
| sales letter | 0.1158 | 2 | YES |
| seo book | 0.1158 | 2 |  |
| landing page | 0.1072 | 2 |  |
| seo industry | 0.0639 | 1 |  |
| industry branding | 0.0639 | 1 |  |

**Top 5 Unigrams by TF-IDF:**

| Unigram | TF-IDF Score |
|---------|-------------|
| seo | 0.1480 |
| link | 0.1184 |
| copy | 0.0882 |
| sales | 0.0852 |
| book | 0.0852 |

**Sample titles (first 8):**

- Does the SEO Industry Have a Branding Problem?
- I am a Shameless Attention Seeker
- How to Write for Google
- The Death of the Long Copy Sales Letter
- Why Linking to Other Blogs is Critical
- And the Verdict on Linkbaiting Is…
- Link Baiting Goes Mainstream
- Is the New SEO Book Sales Letter Working?

## Label Summary

| Cluster | Posts | Label | Quality | Labeling Path |
|---------|-------|-------|---------|--------------|
| 1 | 53 | Content Promotion & Writing | good | Bigram + qualifier |
| 3 | 44 | Social Media & People | good | Bigram + qualifier |
| 0 | 24 | Business Blog & People | acceptable | Top 2 unigrams |
| 2 | 24 | Landing Page & Keyword | good | Bigram + qualifier |

## Label Quality Assessment

| Quality | Count | % | Criteria |
|---------|-------|---|----------|
| Good | 3 | 75% | Bigram-based, descriptive, no function words |
| Acceptable | 1 | 25% | Unigram pair or single word |
| Bad | 0 | 0% | Contains function/archaic words (whom, thee, etc.) |
| Vague | 0 | 0% | Generic fallback ("General Content", "Miscellaneous") |

### Fallback Chain Distribution

| Path | Count | Description |
|------|-------|-------------|
| Best bigram | 0 | Top bigram with score > 0 and freq >= 2 |
| Bigram + qualifier | 3 | Best bigram + top unigram not in bigram |
| Top unigrams | 1 | No qualifying bigram; joined top 2 unigrams |
| Fallback | 0 | "General Content" or "Miscellaneous" |

## Processing Summary

| Step | Time | Notes |
|------|------|-------|
| Crawl (Step 1 prerequisite) | 102.0s | 148 URLs |
| Clustering (Step 6 prerequisite) | 52.5s | Synthetic embeddings |
| Site stop word detection | 5.05ms | 0 words stopped |
| TF-IDF labeling (all clusters) | 147.9ms | 4 clusters |
|   Cluster 1 (53 posts) | 7.5ms | "Content Promotion & Writing" |
|   Cluster 3 (44 posts) | 5.2ms | "Social Media & People" |
|   Cluster 0 (24 posts) | 3.0ms | "Business Blog & People" |
|   Cluster 2 (24 posts) | 4.5ms | "Landing Page & Keyword" |
| **Total Step 6b** | **152.9ms** | **Free (zero API calls)** |

## Observations

1. **No site-wide stop words detected** -- closest word 'blog' at 11/145 (8%), needs 29 (30%). Copyblogger titles are too diverse for the 145-post subset. Labels may contain site vocabulary that would be stopped on larger crawls.

2. **Format stripping modified 19/145 titles (13%).** Most Copyblogger titles are short blog-style headlines (not 'The Definitive Guide to X'), so format markers are rare. The main stripping comes from trailing patterns (site name, year references).

3. **3/4 clusters labeled via bigram path** -- bigrams produce more readable labels ('Content Promotion' vs 'Content'). The freq >= 2 requirement ensures the bigram appears in multiple titles, not just once by coincidence.

4. **All 4 labels are unique** -- no duplicate labels. TF-IDF's inverse document frequency naturally pushes clusters toward different words.

5. **Label quality: 3 good, 1 acceptable, 0 vague.** All labels are at least acceptable.

6. **Total labeling time: 152.9ms** for 4 clusters. TF-IDF labeling is effectively free -- pure Python text analysis with no API calls, no ML models, no GPU. Even a 1000-post site with 40 clusters would complete in < 1 second.

7. **Phrase extraction yields 6.7 phrases/title on average.** 0 title(s) produced zero phrases (all words were stop words or format words). These titles contribute nothing to TF-IDF scoring and dilute cluster signal.

8. **Synthetic embeddings produce different clusters than real OpenAI embeddings.** The cluster boundaries here are based on keyword injection, not semantic similarity. TF-IDF labels are still valid because they operate on title text, not embeddings. However, different cluster composition means different label results.

9. **4 label(s) use '&' qualifiers.** The '&' connector appears when either: (a) a bigram is qualified by a top unigram not already in the bigram (e.g., 'Link Building & Outreach'), or (b) no bigram qualified and top 2 unigrams are joined (e.g., 'Sales & Seo').

---

*Report generated by `backend/scripts/test_step6b_e2e.py` -- no database, no API calls.*