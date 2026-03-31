# Step 1 E2E Test Results: copyblogger.com

**Date:** 2026-03-28 13:33
**Target:** `https://copyblogger.com/sitemap.xml`
**Max pages cap:** 150

---

## 1. Crawl Summary

| Metric | Value |
|--------|-------|
| **Duration** | 102.6s |
| **URLs discovered** | 150 |
| **Posts extracted** | 148 |
| **Posts after dedup** | 145 |
| **Duplicates removed** | 3 |
| **URLs skipped** | 2 |
| **Extraction rate** | 98.7% | 
| **Avg time per URL** | 0.68s |

### Skip Reasons

| Reason | Count |
|--------|-------|
| too_few_words (19 words) | 1 |
| too_few_words (18 words) | 1 |

### Sample Skipped URLs (first 10)

- `https://copyblogger.com/has-problogger-been-hacked/` — too_few_words (19 words)
- `https://copyblogger.com/thank-you/` — too_few_words (18 words)

## 2. Normalization Results

| Metric | Value |
|--------|-------|
| **Nav links removed** | 143 |
| **Sitewide headings removed** | 143 |
| **URL duplicates removed** | 3 |

## 3. Content Statistics

| Metric | Value |
|--------|-------|
| **Total posts** | 145 |
| **Avg word count** | 2395 |
| **Median word count** | 1977 |
| **Min word count** | 186 |
| **Max word count** | 14267 |
| **Total words** | 347,264 |

### Page Type Distribution

| Type | Count | % |
|------|-------|---|
| blog | 142 | 97.9% |
| landing | 1 | 0.7% |
| product | 1 | 0.7% |
| glossary | 1 | 0.7% |

### Language Distribution

| Language | Count |
|----------|-------|
| en | 145 |

### HTTP Status Codes

| Status | Count |
|--------|-------|
| 200 | 145 |

## 4. Field Coverage

| Field | Has Value | Missing | Coverage |
|-------|-----------|---------|----------|
| publish_date | 145 | 0 | 100.0% |
| modified_date | 2 | 143 | 1.4% |
| meta_description | 19 | 126 | 13.1% |
| headings | 46 | 99 | 31.7% |
| language | 145 | 0 | 100.0% |

## 5. Internal Link Graph

| Metric | Value |
|--------|-------|
| **Total internal links** | 973 |
| **Posts with >= 1 link** | 145 (100.0%) |
| **Avg links per post** | 6.7 |
| **Resolvable (target is a known post)** | 42 (4.3%) |
| **Unresolvable (target not in posts)** | 931 |
| **Nav links filtered out** | 143 |

## 6. Heading Structure

| Level | Total Count | Avg per Post |
|-------|-------------|-------------|
| H1 | 1 | 0.0 |
| H2 | 20 | 0.1 |
| H3 | 190 | 1.3 |

## 7. Longest Posts (Top 5)

| # | Title | Words | URL |
|---|-------|-------|-----|
| 1 | How to Write Ebooks that Sell | 14,267 | `/create-ebooks-that-sell` |
| 2 | Does Telling Someone to "Click Here" Work? | 10,543 | `/click-here` |
| 3 | Six Common Punctuation Errors that Bedevil Bloggers | 9,516 | `/punctuation-mistakes` |
| 4 | The Snowboard, the Subdural Hematoma, and the Secret of Life | 8,227 | `/the-secret-of-life` |
| 5 | Twitter Writing Contest: Win an IPod Nano For the Best 140 C... | 8,173 | `/twitter-writing-contest` |

## 8. Shortest Posts (Bottom 5)

| # | Title | Words | Page Type | URL |
|---|-------|-------|-----------|-----|
| 1 | Copyblogger - Content marketing tools and training. | 186 | landing | `/` |
| 2 | Tubetorial Sold to SplashPress Media | 472 | blog | `/tubetorial-sold-to-splashpress-media` |
| 3 | The SEOmoz Landing Page Contest: Entries Judged by Live Mult... | 503 | blog | `/the-seomoz-landing-page-contest-entries-judged-by-live-multivariate-testing` |
| 4 | Do You Spend $10,000 a Month on Pay Per Click Ads? | 546 | blog | `/do-you-spend-10000-a-month-on-pay-per-click-ads` |
| 5 | Here's Some Cool Copy for July 4th | 553 | blog | `/heres-some-cool-copy-for-july-4th` |

## 11. Sample Post (Full Detail)

**URL:** `https://copyblogger.com/how-to-be-a-rock-star-in-your-niche`
**Title:** How to be a Rock Star in Your Niche
**Slug:** how-to-be-a-rock-star-in-your-niche
**Word Count:** 2065
**Page Type:** blog
**Language:** en
**HTTP Status:** 200
**Publish Date:** 2007-07-06 00:00:00+00:00
**Modified Date:** None
**Content Hash:** `3c7949310dc1a950a8f51fe794ebf0c247c922386dc460bcbd04e10652a2e706`
**Meta Description:** None
**Categories:** []
**Tags:** []
**Internal Links:** 4
**Headings:** 0

**Internal Links (first 10):**

- [far from dead](https://copyblogger.com/blogging-is-dead/)
- [Copyblogger](https://copyblogger.com/subscribe/)
- [Personal Branding](https://copyblogger.com/category/personal-branding/)
- [Social Media Marketing](https://copyblogger.com/category/social-media/)

**Body Text (first 500 chars):**
```
Want to be a celebrity?
You can be.
I’m not talking about being famous like Tom Cruise. You’re likely too tall to pass for Tom Cruise, even if you’re female.
What I’m talking about is being the name that pops in a person’s head when a certain area of expertise is mentioned. You want to be the go-to individual for that particular niche, especially when a citation, quote, or interview is necessary for the media (social and traditional).
Business people have been writing articles for trade publicat
```

## 12. Robots.txt & Crawl Behavior

- **User-Agent:** `Tended/0.1 (Content Intelligence Bot)`
- **Rate limit:** 2 req/sec (shared domain limiter)
- **Concurrency:** 10 concurrent fetches
- **Timeout:** 30s per URL
- **Retries:** 3 per URL
- **robots.txt filtering:** Applied (URLs disallowed for Tended user-agent excluded)
