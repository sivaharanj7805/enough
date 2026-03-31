# Tended — PDF Audit Report Specification

**Version:** 5.0 — March 27, 2026
**Single source of truth. Every rule is binary: pass or fail.**
**If any rule fails, the report does not ship.**

---

## PART 1: GLOBAL RULES

### 1.1 — Number Rules

- [ ] Every number that represents quality (scores, percentages, overlap) is colored by its value: red <30, amber 30-55, green >55
- [ ] Every number has context: at minimum a label, ideally a judgment word (poor/moderate/good) or a comparison
- [ ] No number appears without a unit or denominator ("/100", "%", "posts", "pairs")
- [ ] Problem numbers and neutral numbers are never the same color. The "Issues Found" stat box is red. The "Posts Analyzed" and "Topic Clusters" stat boxes are dark grey
- [ ] The health score on the cover matches the health score on page 2 matches the health score bar marker. All three show the same number
- [ ] Recommendation count is the actual count from the database, not rounded or estimated
- [ ] Post counts, cluster counts, issue counts, and pair counts are exact integers from the database — no rounding, no estimates
- [ ] All mentions of the same number are identical across every page
- [ ] No number in the report contradicts another number visible on the same page or the immediately preceding page. If "23" appears in one line, "55+" cannot appear two lines below it referencing the same thing
- [ ] No element depends on color alone to communicate meaning. Every red number also has a label word ("poor"), every green number also has a label word ("healthy"). A prospect viewing in greyscale or low-brightness still gets the message

### 1.2 — Text Rules

- [ ] No paragraph exceeds 4 lines at 11pt body text within the content area
- [ ] No sentence exceeds 25 words. Count every sentence before rendering. If any sentence is 26+ words, split it. Exception: locked templates are immutable and exempt from this rule — they were tested across iterations and their sentence length is intentional. This exception applies ONLY to the exact locked template sentences in Part 2, not to any generated or modified text
- [ ] No jargon appears without a plain-language explanation in the same sentence. "Cannibalization" → "content overlap." "Orphan posts" → "posts with no internal links." "Schema markup" → "structured data (schema markup)" on first use, then "structured data" after
- [ ] No problem is stated without a consequence in the same bullet or sentence. "47 orphan posts" fails. "47 orphan posts — no internal links, invisible to crawlers" passes
- [ ] Bold is used ONLY for: key numbers within sentences, the most important Key Finding bullet, "Week N" labels, post titles in the Example Fix, and section sub-headers. Nothing else is bolded
- [ ] Red text (#DC2626) is used ONLY for: the urgency sentence on the cover, the fourth Key Finding bullet, the comparative context line on page 2, the Schema "0/100" dimension box, and the CTA urgency line. Maximum 5 red text elements in the entire report
- [ ] Green text (#059669) is used ONLY for: the AI citability positive bullet in Content Profile, Quick Win impact lines, and the "What You Get" checkmarks. Maximum 6 green text elements in the entire report
- [ ] The prospect's domain name appears on every page — either in body text, a section header, or the footer
- [ ] The prospect's domain is written exactly as crawled ("backlinko.com") — never converted to a brand name ("Backlinko"), never capitalized differently, never shortened. This applies everywhere: summary paragraph, Key Findings, Quick Wins, Example Fix, 30-Day Plan
- [ ] No sentence in the report makes a promise about what will happen if the prospect fixes an issue. "Adding structured data enables rich results" is a pass (states a capability). "Adding structured data will increase your traffic by 30%" is a fail (promises an outcome). "Enables," "qualifies for," "increases eligibility" are safe. "Will boost," "guarantees," "will increase" are not. The promise rule distinguishes MECHANICAL outcomes from EXTERNAL outcomes: mechanical outcomes happen by definition when the action is taken ("Eliminate ranking competition between these 2 pages" passes because consolidation mechanically removes the competition; "Restore crawl visibility for 47 posts" passes because adding internal links mechanically makes them crawlable). External outcomes depend on third-party systems ("Increase your traffic," "Boost your rankings" fail because they depend on Google). Test: if the prospect does the action, does the outcome happen with certainty? If yes, it's mechanical and allowed
- [ ] No sentence in the report uses pushy implementation language in analytical sections. "Requires immediate implementation," "must be addressed urgently," and "critical gap requiring action" belong in the Action Plan and CTA — not in the Executive Summary or AI Readiness sections. Analysis sections state facts. Action sections tell the prospect what to do
- [ ] The generator never "polishes" blunt factual language into softer corporate language. "We found 628 content issues" is always better than "The audit identified significant areas for improvement." "Moderate issues that need attention" is always better than "significant improvement opportunities." After every generation, compare to the locked templates in Part 2. If the generated text is softer or vaguer than the template, revert to the template
- [ ] No line of text spans the full content width at body size (11pt). Maximum line length is 85 characters
- [ ] Every sentence starts with a capital letter. A lowercase first word anywhere in the report is a rendering bug and a fail
- [ ] No section header wraps to a second line. If a header is too long for one line, shorten it — do not add parenthetical synonyms to headers. "Top Cannibalization Pairs" passes. "Top Content Overlap (Cannibalization) Pairs" wrapping to two lines fails

### 1.3 — Layout Rules

- [ ] The report is exactly 5 pages. Not 4 (too thin for the price point). Not 6 (the CTA must not be a standalone page). If content doesn't fit in 5 pages, cut elements using the priority order in Part 5. If content is too sparse for 5 pages, add one cluster to the cluster table or expand the cannibalization table from 6 to 8 pairs
- [ ] The CTA section ("What You Get" + "Get all [N] recommendations" + pricing) is on the same page as the 30-Day Action Plan. They are one unit. A page break between the plan and the CTA is a fail
- [ ] No page contains only sales content with no analytical content
- [ ] No page contains only data with no interpretation
- [ ] Every page is 80-95% utilized. No page has more than 15% dead space
- [ ] No section header appears at the bottom of a page without at least 3 lines of its content on the same page. If the content would start on the next page, move the header to the next page too
- [ ] No table header appears on a different page from the table's first data row
- [ ] The cover page content block is vertically centered with equal space above and below (±10% tolerance). This is enforced programmatically with the following algorithm: (1) calculate total_content_height from the top of "tended." logo to the bottom of "tended.app," (2) calculate top_padding = (page_height - footer_height - total_content_height) / 2, (3) set the top margin of the content block to top_padding. If this algorithm is not implemented in the PDF generator, it must be before the next report ships. Eyeballing is not acceptable — the cover has failed vertical centering in every iteration to date
- [ ] Adjacent pages do not have dramatically different density. If page 2 is 95% utilized and page 3 is 60% utilized, redistribute content
- [ ] Every visual container (Key Findings box, Content Profile box, "What this means" box, Example Fix box, 30-Day Plan box, What You Get box) has: background tint, 1px border, 12px internal padding, 4px border-radius
- [ ] Thin divider lines (#E5E7EB, 1px) appear between major sections on the same page but NOT between every element
- [ ] The footer on every page is identical: thin grey line + "Tended · [domain] · [date] · Page N" in 9pt #9CA3AF. No logos, dashes, or artifacts in the footer
- [ ] All text is legible at 50% zoom (simulates phone PDF preview). If any text is unreadable below 10pt at full size, increase it
- [ ] The cover page score number (72pt) is legible in a thumbnail preview — a prospect scrolling their DMs sees the number before they tap to open

### 1.4 — Terminology Rules

- [ ] First mention of any technical concept uses the full form: "structured data (schema markup)." All subsequent mentions use "structured data" only
- [ ] The term "schema" or "schema markup" appears in exactly one context: the AI Readiness dimension box label (because "Schema" is shorter and fits the box). Everywhere else — including Quick Win headers, Quick Win descriptions, Quick Win impact lines, the "What this means" box, the 30-Day Action Plan, Key Findings, and the Example Fix — the term is "structured data" or "FAQ structured data." No exceptions
- [ ] Run a literal find-and-replace before render. The following terms trigger replacement if found ANYWHERE outside the dimension box label:
  - "schema markup" → "structured data"
  - "schema" (standalone word) → "structured data"
  - "JSON-LD" → remove or replace with "structured data"
  - "FAQPage" → "FAQ structured data"
  - "FAQPage schema" → "FAQ structured data"
  - "FAQPage schema markup" → "FAQ structured data"
  - "Article schema" → "Article structured data"
  This find-and-replace is automated and runs on the FINAL rendered text, not just the templates. It catches any terminology that the generator introduces regardless of whether locked templates were used
- [ ] "Cannibalization" is always preceded or followed by "content overlap" on first use per page. After first use on a page, "overlap" alone is acceptable
- [ ] "Orphan posts" always includes "no internal links" in the same sentence or parenthetical. Exception: this rule applies to GENERATED text only, NOT to locked templates. If a locked template uses "orphan posts" without the explanation, the explanation must appear elsewhere on the same page (e.g., Key Finding bullet #2). The rule is satisfied by page-level context when inside a locked template
- [ ] "E-E-A-T" is never spelled out — the audience knows the acronym
- [ ] The structured data / schema finding appears in exactly 4 places and no more: (1) cover urgency sentence, (2) Key Finding #4, (3) AI Readiness "Why AI systems skip" bullets, (4) CTA urgency line
- [ ] Before rendering, run a literal count of every sentence that references structured data, schema, or the 0% finding. If the count exceeds 4, delete mentions in this order: (1) summary paragraph sentence, (2) "What this means" box reference, (3) Quick Win description. The four protected locations above are never cut
- [ ] The comparative context line on page 2 does NOT count toward the 4-mention limit because it references the concept qualitatively ("standard practice"), not the specific finding ("0% of your posts have…")
- [ ] The automated find-and-replace does NOT run on text that already contains "structured data." If the input is "structured data (schema markup)," the output must remain unchanged — not "structured data (structured data)." The replacement checks adjacency before replacing
- [ ] The find-and-replace does NOT run on locked template output that was correctly populated. Double-replacement is a rendering bug worse than the original inconsistency

### 1.5 — Brand Rules

- [ ] A brand descriptor line appears directly below the "tended." logo on the cover: "AI Content Audit Platform" in #9CA3AF, 10pt, Regular, with 4px spacing below the logo
- [ ] The brand descriptor does not appear on any page other than the cover
- [ ] The brand descriptor does not use marketing language ("The #1 AI Audit Tool" is a fail, "AI Content Audit Platform" is a pass)
- [ ] A prospect who has never heard of Tended can identify what category of tool produced this report within 2 seconds of seeing the cover
- [ ] "tended." logo is in brand blue (#2563EB)
- [ ] "tended.app" appears on the cover in brand blue
- [ ] Footer says "Tended" not "Enough"
- [ ] CTA says "with Tended" not "in Enough"
- [ ] No references to old brand name anywhere

### 1.6 — File & Metadata Rules

- [ ] PDF file size is under 2MB. Over 2MB and LinkedIn/Twitter DM preview won't render it
- [ ] PDF metadata title is "[domain] Content Audit — Tended" not "output.pdf" or "report_final_v3.pdf"
- [ ] PDF metadata author is "Tended" not blank, not your personal name, not "ReportLab" or "WeasyPrint"
- [ ] The tended.app URL on the cover and in the CTA is a real clickable hyperlink, not plain text

---

## PART 2: PAGE-BY-PAGE SPECIFICATION

### Page 1 — Cover

**Purpose:** One emotional reaction: "I need to read this."

**Elements (top to bottom, all centered, vertically centered as a block on the page):**

1. **"tended." logo** — brand blue (#2563EB), 14pt, Inter Medium
1b. **"AI Content Audit Platform"** — #9CA3AF, 10pt, Regular. Directly below the logo with 4px spacing. Remove after 1,000+ reports sent
2. **Domain name** — as-crawled ("backlinko.com") in #111827, 36-42pt, Bold. Largest text on page
3. **"Content Audit Report"** — #9CA3AF, 14pt, Regular
4. **"[Date]"** — #9CA3AF, 12pt, Regular
5. **40px vertical space**
6. **Health score** — score in 72pt Bold, colored by value. "/100" in 36pt Regular #9CA3AF, baseline-aligned
   - Color thresholds: red (#DC2626) if <30, amber (#D97706) if 30-59, yellow-green (#65A30D) if 60-74, green (#059669) if 75+
7. **"Content Health Score"** — #9CA3AF, 12pt, Regular
8. **Score label** — #9CA3AF, 11pt, italic. Below 30: "(poor)". 30-44: "(below average)". 45-59: "(moderate)". 60-74: "(good)". 75+: "(excellent)"
9. **GA4 disclaimer** — #9CA3AF, 10pt, italic: "Based on content analysis — connect Google Analytics for a complete score"
10. **40px vertical space**
11. **Urgency sentence** — #DC2626, 16pt, Bold, centered. One sentence. Site-specific
12. **"tended.app"** — #2563EB, 12pt, Regular. Clickable hyperlink

**Urgency sentence priority order:**

| Priority | Condition | Template |
|----------|-----------|----------|
| 1 | schema_pct = 0% | "100% of your posts have zero structured data — AI systems can't cite what they can't read." |
| 2 | cann_post_pct > 40% | "[N]% of your posts are competing against each other for the same searches." |
| 3 | meta_desc_pct = 0% | "Zero meta descriptions across all [N] posts — search engines write your snippets for you." |
| 4 | eeat_score < 10 | "Your site has no visible author information — AI systems don't cite anonymous content." |
| 5 | orphan_pct > 30% | "[N] of your pages have zero internal links — invisible to Google's crawler." |
| 6 | Fallback | "[N] content issues found across [N] posts — [top issue type] is your biggest gap." |

**Urgency sentence rules:**
- [ ] Contains a specific number from the actual site data (not rounded, not estimated)
- [ ] States a consequence, not just a fact
- [ ] Is one sentence, maximum 20 words
- [ ] Does not use jargon the prospect wouldn't know ("structured data" is okay, "JSON-LD" is not for the cover)
- [ ] Is different from the CTA urgency line on page 5 (same finding is fine, same sentence is not)

**Cover checklist:**
- [ ] Domain name is exactly as crawled (no "www." added or removed)
- [ ] Score matches the database value (not rounded)
- [ ] Score color matches the value threshold
- [ ] Label word matches the score range
- [ ] "tended.app" is in brand blue and is a clickable hyperlink
- [ ] Footer shows "Tended · [domain] · [date] · Page 1"
- [ ] No stat boxes, bullets, charts, or tables on this page — the cover is emotional, not analytical
- [ ] Content block is vertically centered (±10% tolerance) — enforced programmatically using the algorithm in Section 1.3
- [ ] No more than 15% dead space below the last element

---

### Page 2 — Executive Summary

**Purpose:** If the prospect reads one page, this is it.

**Top border:** 3px #3B82F6 (blue)

#### Summary Paragraph

"Executive Summary" — 24pt Bold #111827.

**LOCKED TEMPLATE — do not rephrase, do not "polish," do not paraphrase. Fill in the brackets with database values:**

Paragraph 1: "Your site **[domain]** scored **[score]/100** on content health, meaning your content ecosystem is showing [label] issues that need attention. We generated **[rec_count] specific recommendations** across your content."

Paragraph 2: "We found **[issue_count] content issues** ([thin_count] thin-content pages, [orphan_count] orphan posts) and **[cann_pair_count] cannibalization pairs** where [cann_post_count] of your [total_posts] posts have significant content overlap."

- [ ] The generator uses the EXACT template above, substituting only the bracketed values. It does NOT rephrase, restructure, or "improve" the template language
- [ ] If the generated output does not match the template structure, regenerate. The template was chosen because it is direct, specific, and fact-stating. Every alternative tested across 10+ iterations was worse
- [ ] Every number in brackets is the exact database value
- [ ] The label word ("moderate") matches the score range defined on page 1
- [ ] No number is rounded (628 not "~600" or "600+")
- [ ] Both paragraphs together do not exceed 6 lines
- [ ] The prospect's domain is written exactly as crawled
- [ ] The issue count (628) appears in both the stat box AND the summary paragraph text
- [ ] No sentence ends with vague purpose phrases ("for improvement," "for optimization," "for enhanced performance")
- [ ] The summary paragraph does NOT contain a sentence about structured data / schema. That finding belongs in Key Findings bullet #4, not here. If the generator adds a schema sentence to the summary, delete it before rendering
- [ ] The locked template is treated as immutable code. The generator substitutes bracketed values and outputs the result. It does not restructure sentences, add parenthetical explanations, split sentences, or insert jargon definitions. If the output structure differs from the template, revert to the template

#### Stat Boxes

Three boxes, horizontal, equal width, inside #F9FAFB container with 1px #E5E7EB border:

| Box | Number | Number Color | Label |
|-----|--------|-------------|-------|
| 1 | [total_posts] | #374151 (neutral) | Posts Analyzed |
| 2 | [cluster_count] | #374151 (neutral) | Topic Clusters |
| 3 | [issue_count] | #DC2626 (RED) | Issues Found |

- [ ] Box 3 (Issues Found) is ALWAYS red regardless of the number
- [ ] Boxes 1 and 2 are ALWAYS dark grey
- [ ] Numbers are 32pt Bold. Labels are 11pt Regular #9CA3AF
- [ ] Numbers are exact database values
- [ ] Labels are plain language ("Issues Found" not "Anomalies Detected")

#### Recommendation Variety Preview (optional)

Insert below stat boxes, above Key Findings. First element to cut if page exceeds 90% utilization.

- [ ] One line in 10pt #9CA3AF italic: "Includes: structured data additions, meta description rewrites, internal linking maps, content consolidation briefs, FAQ section templates, heading restructures, and freshness date additions."
- [ ] Lists exactly 7 recommendation types
- [ ] Every type listed actually exists in the recommendation database for this specific site
- [ ] No two types are synonymous ("meta description rewrites" and "meta description improvements" is a fail)

#### Key Findings

"Key Findings" — 16pt Bold. Inside #F9FAFB container (1px #E5E7EB border, 12px padding).

Four bullets. Generated from the top 4 findings sorted by severity. The most severe finding goes LAST (climax ordering).

- [ ] Each bullet contains a specific number ("[N] of your [N] posts")
- [ ] Each bullet states what the problem IS and what the consequence IS in the same sentence
- [ ] First three bullets are in regular #374151 text
- [ ] Fourth bullet (most severe) is in Bold #DC2626 (red) and uses "structured data" — never "schema markup" or "JSON-LD"
- [ ] No bullet exceeds 2 lines
- [ ] No two bullets reference the same finding
- [ ] The locked bullet templates are treated as immutable code. The generator substitutes bracketed values only. It does not append phrases, add em dashes, reword templates, or change "cannibalization pairs detected" to "pairs." If consequences are desired in bullets 1-3, update the spec template first, then update the generator

**LOCKED BULLET TEMPLATES — use these exactly, substituting only the bracketed values:**

| Finding Type | Template |
|-------------|----------|
| Cannibalization | "[cann_post_count] of your [total] posts have significant content overlap ([pair_count] cannibalization pairs detected)" |
| Orphan posts | "[orphan_count] orphan posts have no inbound internal links" |
| Thin content | "[thin_count] posts are too thin relative to cluster average" |
| Schema (ALWAYS last if present) | "**100% of posts have no structured data — missing Article/FAQ markup that dramatically increases AI Overview citations**" |
| Missing meta | "[meta_missing_count] posts have no meta description — search engines show random text snippets" |
| Low E-E-A-T | "E-E-A-T score is [score]/100 — no visible author information, dates, or credentials" |

#### Health Score Bar

- [ ] The bar is 504pt wide, 12pt tall. Five segments: Red → Orange → Amber → Yellow-green → Green
- [ ] The ▼ marker is positioned at the exact percentage corresponding to the score (54/100 = 54% from left)
- [ ] The score number next to the marker matches the cover score
- [ ] The score number color matches the cover score color
- [ ] Five labels below: "Poor" "Below Avg" "Moderate" "Good" "Excellent" in 9pt grey

#### Content Profile

"Content Profile" — 14pt Bold. Inside #F9FAFB container.

Four bullets with site-specific data:

| Bullet | Data Source | Format |
|--------|-----------|--------|
| Average post length | AVG(word_count) from posts table | "[N] words ([descriptor])" where descriptor is: <500 "short-form", 500-1500 "medium-form", 1500-3000 "long-form", 3000+ "deep-form" |
| Average readability | AVG(flesch_score) from posts table | "Flesch [N] ([descriptor])" where: <30 "very difficult", 30-50 "difficult", 50-60 "fairly difficult/professional audience level", 60-70 "standard", 70-80 "fairly easy", 80+ "easy" |
| Content freshness | % of posts with last_updated within 12 months | "[N]% updated in last 12 months" |
| AI citability | Site-level ai_citability_score | "Your content structure scores [N]/100 on AI citability" — this bullet is **green (#059669) and bold** |

- [ ] All four values come from actual database aggregates, not estimates
- [ ] The word count descriptor matches the actual average
- [ ] The readability descriptor matches the actual Flesch score range
- [ ] The fourth bullet (AI citability) is the ONLY green bold text on this page
- [ ] No bullet references structured data/schema (save for the comparative context line)
- [ ] Every bullet that reports a "good" metric is reframed to surface the gap, not the achievement. "82% updated in last 12 months" alone is a fail. Must append a gap: "— but only [N]% display visible freshness dates for search engines" or "— but [N]% are stale and may drag down cluster health"
- [ ] The Content Profile is NOT a praise section. It is context that makes problems feel more urgent. If a bullet sounds like a compliment with no qualifier, it is a fail
- [ ] Exception: the AI citability bullet IS positive and green — this is the one "you're doing something right" moment that makes the rest feel credible rather than adversarial

#### Comparative Context

One line. Red (#DC2626), Bold, 12pt.

**LOCKED TEMPLATE:** "Structured data is standard practice for content sites competing in AI Overviews — yours has none."

- [ ] Uses qualitative language ("standard practice," "typically") not unverifiable quantitative claims
- [ ] Contains no unverifiable statistics
- [ ] Never uses "majority," "most," or a specific percentage comparing the prospect to a benchmark you cannot link to a published study
- [ ] This line does NOT count toward the 4-mention schema limit because it references the concept qualitatively

---

### Page 3 — AI Readiness + Issue Breakdown

**Purpose:** The differentiator — "this tool sees something others don't."

**Top border:** 3px #3B82F6 (blue)

#### AI Readiness

"AI Readiness" — 24pt Bold.

**LOCKED HEADLINE TEMPLATE:** "Your content scores **[citability]/100** on AI citability — but **[schema]/100** on structured data."

- [ ] The citability score is colored green if >55, amber if 30-55, red if <30
- [ ] The schema score is colored red if <30, amber if 30-55, green if >55
- [ ] Both numbers come from the actual site-level scores in the database
- [ ] The headline uses "structured data" not "schema markup"

**Dimension Boxes:** Four boxes in a row.

| Dimension | Label in Box | Score Source | Color Rule |
|-----------|-------------|------------|------------|
| Citability | Citability | ai_citability_score | Green >60, amber 30-60, red <30 |
| E-E-A-T | E-E-A-T | eeat_score | Green >60, amber 30-60, red <30 |
| Schema | Schema | schema_score | Green >60, amber 30-60, red <30 |
| Extraction | Extraction | extraction_score | Green >60, amber 30-60, red <30 |

- [ ] Each score is from the database, not calculated in the PDF template
- [ ] Colors strictly follow the thresholds above
- [ ] Schema at 0 must be in red (#DC2626) and bold — it must visually scream
- [ ] Numbers are 24pt Bold. Labels are 10pt Regular #9CA3AF
- [ ] The dimension box label "Schema" is the ONLY place in the entire report where the word "schema" appears without "structured data." This is acceptable because the box is too narrow for "Structured Data"

**Spider/Radar Chart:**
- [ ] Four axes: Citability (top), E-E-A-T (right), Schema (bottom), Extraction (left)
- [ ] Polygon connects actual score values
- [ ] Fill: #3B82F6 at 15-20% opacity
- [ ] Stroke: #3B82F6 at 100%, 2pt
- [ ] Grid lines at 50 and 100 in #F3F4F6
- [ ] Chart is 200-220pt tall, centered (larger than other elements to serve as visual anchor)
- [ ] If Schema is 0, the polygon visibly collapses to the center on the bottom axis

**"Why AI systems skip your content" bullets:**

- [ ] Each bullet has TWO parts separated by an em dash: the finding and the consequence
- [ ] Numbers come from actual site data (13% question headers, 11% FAQ sections)
- [ ] Target numbers (30% for question headers) are industry benchmarks you can defend
- [ ] No bullet contains a specific multiplier ("2x", "2.5x") unless sourced. "Significantly higher" is acceptable
- [ ] Maximum 3 bullets in this section
- [ ] All bullets use "structured data" not "schema markup"

**"What this means" box:**

Inside #FFF7ED container, #FDBA74 border, 12px padding. Text in #92400E.

**LOCKED TEMPLATE — exactly 2-3 sentences, fill in brackets only:**

Sentence 1: "Without structured data, your posts are invisible to Google's rich results and less likely to be cited in AI Overviews."

Sentence 2: "Adding Article structured data is the single highest-impact change you can make."

Sentence 3 (optional, include only if page space allows): "Google AI Overviews now appear on ~50% of searches."

- [ ] The box uses the EXACT template above. The generator does NOT rephrase, expand, or "enrich" it
- [ ] The box contains exactly 2-3 sentences. 4+ sentences is a fail. Count before rendering
- [ ] Every sentence is under 25 words. Count before rendering
- [ ] Every sentence starts with a capital letter
- [ ] No number appears in the box that isn't already introduced elsewhere in the report
- [ ] The box uses "structured data" not "schema markup"
- [ ] The separate red urgency line below the box is REMOVED. The page already has enough red
- [ ] All statistical claims are from published, findable industry research
- [ ] The box does NOT contain: implementation timelines ("immediately"), percentage claims not on the page ("71.8%"), score references that require context ("those with citability scores of 60 or above"), or any number not already visible on this page

#### Issue Breakdown

"Issue Breakdown" — 16pt Bold.

Four rows, each with: colored dot + count + description + consequence.

| Severity | Dot Color | Issue Types |
|----------|----------|-------------|
| High | Red (#DC2626) | Thin content, orphan posts, near-duplicates |
| Medium | Amber (#D97706) | SEO issues (title, meta, headings), content overlap pairs |
| Low | Yellow (#EAB308) | Minor formatting issues (if shown) |

- [ ] Dot color matches severity, not issue type
- [ ] Every description includes a consequence after an em dash
- [ ] Counts are exact database values
- [ ] The overlap pairs row says "[N] posts may dilute each other" not "[N] posts compete for the same keywords" (you don't have keyword data)
- [ ] Maximum 4 rows. If there are more issue types, combine minor ones

---

### Page 4 — Clusters + Quick Wins + Top 5

**Purpose:** From analysis to action. If it exceeds capacity, the cluster table shrinks first — never the Quick Wins or Top 5.

**Top border:** 3px #059669 (green)

#### Topic Clusters

"Topic Clusters" — 14pt Bold.
"Your content organizes into [N] topic clusters. Top [N] shown." — 10pt #9CA3AF.

Table: Cluster | Posts | Health | Status

- [ ] Shows top 3-5 clusters by post count (use 3 if page is tight, 5 if page has room)
- [ ] Health score numbers are colored: green >55, amber 45-55, red <45
- [ ] Status words are colored: "Healthy" in green (#059669), "Declining" in red (#DC2626), "Growing" in teal (#0891B2)
- [ ] Health number color and status word color agree — if status is "Declining" the health number must be amber or red, never green
- [ ] Cluster labels are Claude-generated human-readable names, not TF-IDF word salad
- [ ] "Posts" column is plain dark grey (neutral count)
- [ ] Table header and first data row are on the same page. No orphaning across page breaks
- [ ] At least one non-"Healthy" cluster is visible (if one exists) to show the tool differentiates
- [ ] If the spread between the highest and lowest cluster health scores is less than 8 points, the status labels are based on a DIFFERENT signal than the health score alone — use trend direction (freshness increasing/decreasing) or structural health (orphan posts, thin posts). A cluster labeled "Declining" must NOT have a health score within 3 points of a cluster labeled "Healthy"
- [ ] If the spread is 8+ points, health score alone is sufficient for status labels
- [ ] A 9pt footnote appears below the cluster table: "Status based on content freshness trends and structural health, not score alone"

#### Top 3 Quick Wins

"Top 3 Quick Wins" — 24pt Bold.

Each Quick Win has three parts:
1. **Bold numbered header** — the action
2. **1-2 sentence description** — what is wrong with THIS site and what happens when they fix it
3. **Green impact line** — the specific outcome

**QUICK WIN ASSEMBLY — THIS IS A TWO-STEP PROCESS, NOT A SINGLE GENERATION:**

**Step 1: Select the three Quick Win TYPES.** Quick Win #1 is always structured data (if schema = 0%). Quick Win #2 is always the top cannibalization pair. Quick Win #3 rotates based on site data — choose ONE from the locked templates below.

**Step 2: For each selected type, use ONLY its locked template.** The header, description, and impact line come from the SAME template row. They are never mixed across rows. This is the rule that prevents the header/body mismatch bug.

**LOCKED QUICK WIN TEMPLATES:**

**Quick Win #1 — Structured Data (always if schema = 0%):**
- Header: "Add structured data to your top posts"
- Description: "None of your [total_posts] posts have structured data. Adding it enables rich results and AI citations."
- Impact: "→ Enables rich results for 100% of your [total_posts] posts"

**Quick Win #2 — Top Cannibalization Pair (always):**
- Header: "Consolidate or differentiate: '[Post A truncated]' vs '[Post B truncated]'"
- Description: "These posts are [overlap]% similar and may dilute each other's search visibility."
- Impact: "→ Eliminate ranking competition between these 2 pages"

**Quick Win #3 — Select ONE of the following based on site data. Use the ENTIRE row (header + description + impact). Never mix parts from different rows:**

| Condition | Header | Description | Impact |
|-----------|--------|-------------|--------|
| orphan_count > 20 | "Fix [orphan_count] orphan posts with internal links" | "[orphan_count] posts have no inbound internal links, making them invisible to search crawlers." | "→ Restore crawl visibility for [orphan_count] posts" |
| faq_candidate exists | "Add FAQ structured data: [Post Title]" | "This post has FAQ-style content but no FAQ structured data to make it machine-readable." | "→ Qualifies this post for FAQ rich results" |
| thin_count > 3 | "Expand [thin_count] thin-content posts" | "[thin_count] posts are significantly below your site's average word count and underperform in search." | "→ Bring [thin_count] posts to competitive depth" |
| meta_missing > 30% | "Write meta descriptions for [meta_missing_count] posts" | "[meta_missing_count] posts have no meta description, letting Google generate random snippets." | "→ Control search snippets for [meta_missing_count] posts" |

**QUICK WIN #3 ASSEMBLY VALIDATION — AUTOMATED, RUNS BEFORE RENDERING:**

```
For Quick Win #3:
  1. Read the selected template row
  2. Populate header from that row's Header column
  3. Populate description from that row's Description column
  4. Populate impact from that row's Impact column
  5. VERIFY: Extract the primary noun from the header (e.g., "orphan posts," "FAQ structured data," "thin-content posts," "meta descriptions")
  6. VERIFY: Confirm that primary noun appears in the description text
  7. If the primary noun from the header does NOT appear in the description → FAIL. Regenerate using the correct template row
  8. Run terminology find-and-replace on the final output
```

This validation catches the header/body mismatch bug that persisted across 4 consecutive versions. The bug was caused by the generator selecting a header from one template row and a description from a different row. The validation ensures all three parts come from the same row.

- [ ] All three Quick Wins are DIFFERENT types of recommendations
- [ ] Quick Win #1 is always the highest-impact action
- [ ] Each description is maximum 2 sentences
- [ ] Each impact line starts with "→" in green italic
- [ ] Impact lines contain a specific number when possible
- [ ] Impact lines describe the OUTCOME, not the action
- [ ] Impact lines are not tautological. "Enables structured data across posts without structured data" is a fail. "Enables rich results for 100% of your 149 posts" is a pass
- [ ] No Quick Win references a post pair that doesn't exist in the cannibalization table on page 5
- [ ] Quick Win descriptions are site-specific findings, not definitions. "Structured data helps search engines understand your content type" is a fail — it's a Wikipedia definition. "None of your 149 posts have structured data" is a pass — it's about their site
- [ ] Quick Win descriptions state what is wrong with THIS site, then what happens when they fix it. Problem → outcome. Not concept → explanation
- [ ] Quick Win descriptions do not repeat the action header in different words
- [ ] Quick Win descriptions and impact lines do not reference data the tool doesn't have. No "keyword authority," "keyword rankings," "keyword consolidation," or "traffic increase" unless you have that data
- [ ] **HEADER/BODY COHERENCE CHECK (automated, mandatory):** After generating each Quick Win, extract the primary subject from the header and verify it appears in the description. "Fix 47 orphan posts" → description must contain "orphan" or "internal links." "Add FAQ structured data" → description must contain "FAQ." If the check fails, the Quick Win is regenerated from the correct locked template row. This check has caught a persistent bug across 4 consecutive report versions
- [ ] All Quick Wins use "structured data" — never "schema markup," "JSON-LD," "FAQPage schema markup," or "FAQPage schema." The automated terminology find-and-replace in Section 1.4 catches any that slip through

#### Top 5 Posts Needing Attention

"Top 5 Posts Needing Attention" — 16pt Bold.

Table: # | Post | Score | Issues

- [ ] Shows the 5 lowest-scoring posts by composite health score
- [ ] Posts with word_count < 100 are EXCLUDED (landing pages, job listings, nav pages)
- [ ] Score column is color-coded: red <30, amber 30-55, green >55
- [ ] Scores are a GRADIENT — 26 should be visually darker/more urgent than 39
- [ ] Issues column shows at least 2 specific issues per row + "(+N more)" if there are additional issues. Showing only 1 issue per row is a fail
- [ ] Post titles truncate with "..." only after a meaningful word. No post title is truncated to fewer than 5 words
- [ ] The Score column header is on ONE line (not split). If the column is too narrow, widen it
- [ ] No column header wraps to a second line

---

### Page 5 — Example Fix + Cannibalization + Plan + CTA

**Purpose:** Proof the fixes are real, then evidence, plan, close.

**Top border:** 3px #D97706 (amber)

#### Example Fix

**THIS IS THE SINGLE MOST IMPORTANT CONVERSION ELEMENT AFTER THE COVER URGENCY SENTENCE.**

Inside #EFF6FF container, #93C5FD border, 12px padding.

**Structure:**
1. Header: "**Example Fix — Your lowest-scoring post**" — 14pt Bold. Always this exact text, because we always use the #1 post
2. "**[Post Title]** (score: [N])" — 12pt, score in red
3. If current is (none): "Current: *(none)*". If current exists: "Current: *[actual meta, truncated with ...]*" — 11pt, grey italic
4. If current is (none): "Suggested: **[meta description]**". If current exists: "Improved: **[meta description]**" — 11pt, suggestion in Bold dark blue (#1E40AF). Always shown in FULL, never truncated

Below the container: "*Get AI-written meta descriptions for all [N] posts*" — 10pt #9CA3AF italic

**Rule EF-1: Always use the #1 post.**
- [ ] The Example Fix post is ALWAYS the #1 lowest-scoring post from the Top 5 table. No exceptions. No walking down the list. The #1 post is the example, regardless of whether it has a meta description
- [ ] The header always says "Example Fix — Your lowest-scoring post"
- [ ] The post title in the Example Fix exactly matches the title in the Top 5 table (same truncation, same wording)

**Rule EF-2: The suggested/improved meta description must be SPECIFIC to the actual page content.**
- [ ] It must name at least 2 specific things that are actually on the page
- [ ] It must NOT contain any of these generic phrases: "comprehensive guide," "in-depth analysis," "expert recommendations," "actionable tips," "best practices," "everything you need to know," "key strategies," "practical examples," "learn everything about," "covering key," "This resource covers," "key insights," "actionable strategies"

**Rule EF-3: The suggested meta description must sound like a human copywriter wrote it.**
- [ ] It reads naturally as a search result snippet
- [ ] It's between 120-155 characters
- [ ] It starts with a number or verb, not "This" or "A" or "An"
- [ ] It creates a reason to click

**Rule EF-4: The suggested meta description must be BETTER than what Google would auto-generate.**
- [ ] Clearly superior to a random body sentence pulled by Google
- [ ] If the current meta exists and is already decent, the improvement must change the structure, not just swap synonyms

**Rule EF-5: Numbers must be accurate and preserved.**
- [ ] Every factual claim is verifiable against the actual page content
- [ ] The improved meta description does not inflate any number from the current meta description. If the current says "23 templates," the improved cannot say "55+ templates"
- [ ] If the current meta contains a specific number ("23 detailed marketing templates"), the improved version MUST include that same number. The number is the most concrete proof the tool read the actual page. Dropping it makes the "improvement" less specific than the original
- [ ] Every number in the suggestion exists on the actual page
- [ ] Before rendering, compare: extract all numbers from the "Current" line. Verify each number appears in the "Improved" line. If any number was dropped, regenerate

**Rule EF-6: No filler endings.**
- [ ] The improved meta description does not end with ANY of these patterns:
  - "to grow your business"
  - "to boost your results"
  - "to take your strategy to the next level"
  - "for campaigns and strategy planning"
  - "to optimize your strategy"
  - "& more"
  - "and more"
  - "and much more"
  - "plus more"
  - Any phrase matching the pattern "to [verb] your [noun]" where the noun is generic (business, strategy, results, performance, growth)
  - Any phrase matching "& more," "and more," or "plus more" — open-ended list endings are banned because they signal the tool ran out of specific items to name
- [ ] The final clause names something specific on the page. "Includes editorial calendars, outreach scripts, and audit checklists" is a pass. "For campaigns and strategy planning" is a fail. "& more" is a fail
- [ ] If the current meta is shown truncated, the improved version is shown in FULL — no truncation

**How to generate a passing meta description:**

The Claude prompt must include:
1. The full body_text of the post (or first 2000 characters)
2. The post title
3. The post URL
4. The current meta description (if any) — with explicit instruction: "The current meta says '[exact current meta].' If it contains a number like '23 templates,' your suggestion MUST include that exact number"
5. Explicit instructions: "Write a meta description for this specific page. Name at least 2 specific things that are on this page. Do NOT use generic phrases like 'comprehensive guide', 'expert tips', 'actionable strategies', or 'best practices'. Do NOT end with '& more', 'and more', 'to grow your business', 'for campaigns and strategy planning', or any other vague ending. The last words must name a specific thing from the page. Keep it under 155 characters. Start with a number or verb."

**POST-GENERATION VALIDATION (automated, runs before rendering):**
```
1. Extract all numbers from the "Current" meta description
2. For each number found, check if it appears in the generated suggestion
3. If any number is missing → REGENERATE with explicit instruction to include it
4. Check if the last 4 words match any banned filler pattern
5. If filler detected → REGENERATE
6. Check if any banned phrase from EF-2 list appears → REGENERATE
7. Maximum 3 regeneration attempts, then write manually
```

#### Top Cannibalization Pairs

"Top Cannibalization Pairs" — 24pt Bold.

Intro paragraph (11pt, 1 sentence): "These post pairs cover highly similar topics and may dilute each other's rankings."

- [ ] Shows top 6 pairs by blended overlap score
- [ ] Overlap percentages are color-coded: >85% red (#DC2626), 83-85% dark amber (#B45309), <83% amber (#D97706)
- [ ] Post titles truncate after meaningful words
- [ ] Both Post A and Post B columns are equal width
- [ ] Overlap column is narrow (60pt), right-aligned
- [ ] Every pair shown has been verified by the title-topic-overlap filter (no false positives)
- [ ] The column header says "Overlap" not "Similarity"

#### 30-Day Action Plan

"Your 30-Day Action Plan" — 16pt Bold. Inside #F9FAFB container, 1px #E5E7EB border, 12px padding.

**LOCKED TEMPLATE — substitute bracketed values only:**

- **Week 1:** Add structured data to your top 10 posts
- **Week 2:** Fix [orphan_count] orphan pages with internal links from related content
- **Week 3:** Consolidate '[Post A truncated]' and '[Post B truncated]' ([overlap]% overlap), plus [N] more pairs
- **Week 4:** [Rotate: "Fix [thin_count] thin-content posts by expanding below-average pages" OR "Add FAQ structured data to posts with question-based content" — whichever is NOT the same type as Quick Win #3]

- [ ] Week 1 matches Quick Win #1
- [ ] Every week references a specific number from the report
- [ ] Language is plain
- [ ] "Week N:" is bold. The action text is regular weight
- [ ] No week references an action not supported by the report's findings
- [ ] Week 3 names the specific top pair with its overlap percentage
- [ ] The pair named in Week 3 appears in the cannibalization table on the same page
- [ ] Post titles in the 30-Day Plan truncate at the same point as in the cannibalization table
- [ ] Week 4 is NOT a duplicate of Quick Win #3 — it covers a different action type

#### What You Get

Inside #F0FDF4 container, #86EFAC border, 12px padding.

"**What You Get**" — 16pt Bold.

Three lines with green checkmarks:
- ✓ All [rec_count] recommendations with specific, copy-paste actions
- ✓ AI-ready content briefs for your writers
- ✓ Progress tracking as you fix issues

- [ ] The recommendation count matches the database count and matches the count on page 2 and the CTA
- [ ] Maximum 3 bullet points
- [ ] Checkmarks are green (#059669)

#### CTA

30px space above. Centered.

1. "**Get all [rec_count] recommendations with Tended.**" — 20pt Bold #2563EB
2. "*Every day without structured data, AI systems cite your competitors instead of you.*" — 12pt italic #DC2626
3. "$149/month. 30-day money-back guarantee." — 11pt #9CA3AF
4. "https://tended.app" — 11pt #2563EB, underlined, clickable hyperlink

- [ ] The rec count matches every other mention in the report
- [ ] The urgency line is the SPECIFIC version ("without structured data, AI systems cite your competitors") not the generic version ("start fixing these issues today")
- [ ] Price and guarantee are stated once. Not repeated elsewhere in the report
- [ ] URL is the actual live domain and is a clickable hyperlink
- [ ] CTA is the last element on the page. Nothing below except footer
- [ ] This is the ONLY place in the report that mentions pricing

---

## PART 3: VISUAL SPECIFICATIONS

### Health Score Bar
504pt wide, 12pt tall. Five segments: Red → Orange → Amber → Yellow-green → Green. Labels: "Poor" "Below Avg" "Moderate" "Good" "Excellent" in 9pt grey. ▼ marker at score's percentage + score number in score's color.

### Spider/Radar Chart
200-220pt tall, centered. Four axes in diamond arrangement: Citability (top), E-E-A-T (right), Schema (bottom), Extraction (left). Fill: #3B82F6 at 15-20%. Stroke: #3B82F6 at 100%, 2pt. Grid at 50/100 in #F3F4F6. If one dimension is catastrophically low, the visualization makes that impossible to miss.

### Footer
Thin line (#E5E7EB) + "Tended · [domain] · [date] · Page N" in 9pt #9CA3AF. Identical on every page.

### Section Top Borders
Pages 2-3: Blue (#3B82F6). Page 4: Green (#059669). Page 5: Amber (#D97706).

---

## PART 4: EDGE CASES

- [ ] If the site has fewer than 50 posts, verify the per-post recommendation average is defensible (2-4 per post is credible, 8+ per post invites skepticism)
- [ ] If the site has fewer than 3 cannibalization pairs, the cannibalization table is replaced with a different evidence element or removed entirely
- [ ] If the site scores above 75, the report tone shifts from "problems to fix" to "opportunities to capture." An urgency sentence for a site scoring 82 cannot say "your content is broken"
- [ ] If all Top 5 posts score above 50, the "Needing Attention" framing softens to "Optimization Opportunities"
- [ ] If the site has zero orphan posts, zero thin content, or zero cannibalization pairs, those findings are OMITTED from Key Findings — not shown as "0 found." Showing zeroes wastes space and looks like the tool is searching for problems that don't exist

---

## PART 5: ELEMENT PRIORITY ORDER

### When a page exceeds 95% utilization, cut in this order (lowest priority first):

1. Recommendation variety preview line (page 2)
2. Supporting statistics (third sentence) inside "What this means" box (page 3)
3. Reduce cluster table from 5 to 3 rows
4. Reduce cannibalization table from 8 to 6 pairs
5. Remove the cannibalization intro sentence (keep just the heading + table)
6. Reduce AI Readiness "Why AI systems skip your content" bullets from 3 to 2

### When a page is under 80% utilization, add in this order (highest priority first):

1. Add one more cluster to the cluster table
2. Add one more cannibalization pair
3. Add the recommendation variety preview line to page 2
4. Expand the "What this means" box to 3 sentences (add the optional statistic)

### NEVER cut (load-bearing elements):

- The urgency sentence on the cover
- The brand descriptor on the cover
- The stat boxes on page 2
- The Key Findings bullets on page 2
- The health score bar on page 2
- The spider chart on page 3
- The dimension boxes on page 3
- Quick Win #1 (including its impact line)
- The Example Fix (entire container)
- The "What You Get" box
- The CTA (all 4 lines)
- The 30-Day Action Plan

---

## PART 6: PRE-SEND CHECKLIST

Run every check. If any single check fails, the report does not ship.

### Data Consistency
- [ ] Health score on cover = health score on page 2 = health score bar marker
- [ ] Total posts count is consistent across all mentions
- [ ] Issue count is consistent across all mentions
- [ ] Recommendation count is consistent across all mentions (summary paragraph, What You Get, CTA)
- [ ] Cannibalization pair count matches between page 2 Key Findings and page 5 table
- [ ] Orphan post count matches between page 2 Key Findings, page 3 issue breakdown, and page 5 30-Day Plan
- [ ] All cluster health scores fall within the site's actual range
- [ ] Every number in the Action Plan matches a number elsewhere in the report
- [ ] No post in the Top 5 has word_count < 100

### Example Fix Accuracy
- [ ] The Example Fix post is the #1 lowest-scoring post from the Top 5 table
- [ ] The Example Fix post actually exists on the live site
- [ ] The current meta field reflects the actual live state
- [ ] The suggested/improved meta description doesn't contain banned generic phrases
- [ ] The suggested/improved meta description doesn't end with filler (including "& more," "and more," or any "to [verb] your [noun]" pattern)
- [ ] Every factual claim in the suggestion is verifiable against the actual page
- [ ] If the current meta contains a number, the improved version contains that same number. Automated check: extract numbers from Current, verify they appear in Improved
- [ ] The improved version is shown in full (no truncation)
- [ ] The section header says "Your lowest-scoring post"
- [ ] The post title matches between the Top 5 table and the Example Fix

### Quick Win Accuracy
- [ ] Each Quick Win's header, description, and impact line all came from the SAME locked template row. Verify: the primary subject noun in the header appears in the description
- [ ] Quick Win #3 passed the automated header/body coherence check before rendering
- [ ] Each Quick Win description is site-specific, not definitional
- [ ] Each Quick Win impact line states an outcome, not a tautology
- [ ] No Quick Win contains the terms "schema markup," "JSON-LD," "FAQPage schema," or "FAQPage schema markup." Only "structured data" or "FAQ structured data"
- [ ] No Quick Win references data the tool doesn't have (keywords, traffic)

### Terminology Consistency
- [ ] The automated find-and-replace from Section 1.4 ran on the final rendered text
- [ ] "Schema markup" does not appear anywhere outside the dimension box label
- [ ] "JSON-LD" does not appear anywhere in the report
- [ ] "FAQPage" does not appear anywhere in the report
- [ ] "FAQPage schema" does not appear anywhere in the report
- [ ] The structured data finding is mentioned in exactly 4 places (cover, Key Finding #4, AI Readiness bullets, CTA). Count them

### Visual Accuracy
- [ ] All scores are colored by value (red/amber/green)
- [ ] Schema 0/100 is in red
- [ ] The spider chart polygon collapses correctly for any 0-value axis
- [ ] The weakest dimension is visually dominant
- [ ] Status colors match health score colors in the cluster table
- [ ] No column header wraps to a second line
- [ ] No section header is orphaned from its content
- [ ] No page has >15% dead space
- [ ] Cover content block is vertically centered — verified by the programmatic algorithm in Section 1.3, not by visual inspection
- [ ] Footer is identical on every page

### Text Quality
- [ ] No sentence exceeds 25 words. Automated word count ran on every sentence
- [ ] Every sentence starts with a capital letter
- [ ] No unverifiable statistics appear anywhere
- [ ] No sentence makes outcome promises
- [ ] No analytical section contains pushy implementation language
- [ ] Summary paragraphs match the locked templates (not rephrased)
- [ ] Key Finding bullets match the locked templates (not rephrased)
- [ ] Quick Win #1 and #2 match the locked templates (not rephrased)
- [ ] Quick Win #3 uses its full locked template row (header + description + impact from same row)
- [ ] "What this means" box matches the locked template (not expanded beyond 3 sentences)

### Brand & File
- [ ] "tended." logo is in brand blue
- [ ] Brand descriptor is present on cover
- [ ] Footer says "Tended" not "Enough"
- [ ] No references to old brand name
- [ ] PDF metadata title is "[domain] Content Audit — Tended"
- [ ] PDF metadata author is "Tended"
- [ ] PDF file size is under 2MB
- [ ] All URLs are clickable hyperlinks

---

## PART 7: NARRATIVE ARC

| Page | Emotion | Purpose | The prospect thinks... |
|------|---------|---------|----------------------|
| 1 — Cover | Shock | One number, one consequence | "That doesn't look good" |
| 2 — Summary | Understanding | Full picture, key findings, context | "Okay, now I see the scope of this" |
| 3 — Analysis | Discovery | Your unique angle, the thing other tools don't show | "I haven't seen this before" |
| 4 — Action | Motivation | What to fix, what's worst, proof the fixes are real | "This is specific and doable" |
| 5 — Close | Decision | Evidence, plan, value, price | "I should at least look into this" |

- [ ] Every element on every page serves this arc
- [ ] No page breaks the emotional progression (no sales pitch on page 3, no new analysis on page 5)
- [ ] If an element doesn't advance the prospect toward replying to your DM, remove it

---

## PART 8: PAGE STRUCTURE REFERENCE

| Page | Top Border | Contains |
|------|-----------|----------|
| 1 | None | Cover: logo + descriptor, domain, score, urgency sentence, URL |
| 2 | Blue (#3B82F6) | Executive Summary: locked paragraphs, stat boxes, (optional: variety preview), Key Findings, health bar, Content Profile, comparative context |
| 3 | Blue (#3B82F6) | AI Readiness: headline, dimension boxes, spider chart, "Why AI systems skip" bullets, "What this means" box (locked), Issue Breakdown |
| 4 | Green (#059669) | Topic Clusters table, Top 3 Quick Wins (locked templates with automated coherence check), Top 5 Posts table |
| 5 | Amber (#D97706) | Example Fix (always #1 post, with automated number-preservation and filler-detection), Cannibalization Pairs table, 30-Day Action Plan (locked template), What You Get box, CTA |

- [ ] Page 4 has 3 sections (clusters, quick wins, top 5). Page 5 has 5 sections (example fix, cannibalization, plan, what you get, CTA). If page 5 is too dense, reduce cannibalization table rows first

---

## PART 9: AUTOMATED VALIDATION PIPELINE

These checks run programmatically after generation but before rendering. They are not manual reviews. If any check fails, the component is regenerated automatically.

### 9.1 — Quick Win Coherence Check
```
For each Quick Win:
  header_subject = extract_primary_noun(header)
  description_text = description.lower()
  IF header_subject NOT IN description_text:
    FAIL → regenerate from correct locked template row
```
This catches the header/body mismatch bug (e.g., header about orphan posts, description about FAQ structured data) that persisted across versions 90, 90, 90, and 93.

### 9.2 — Terminology Find-and-Replace
```
For all rendered text OUTSIDE dimension box labels:
  REPLACE "FAQPage schema markup" → "FAQ structured data"
  REPLACE "FAQPage schema" → "FAQ structured data"
  REPLACE "FAQPage" → "FAQ structured data"
  REPLACE "schema markup" → "structured data"
  REPLACE "JSON-LD" → "" (remove) or "structured data"
  REPLACE "Article schema" → "Article structured data"
  REPLACE standalone "schema" (not in "Schema" box label) → "structured data"
```

### 9.3 — Meta Description Validation
```
current_numbers = extract_numbers(current_meta_description)
improved_text = improved_meta_description

FOR each number in current_numbers:
  IF number NOT IN improved_text:
    FAIL → regenerate with explicit instruction to include the number

last_words = improved_text.split()[-4:]
banned_endings = ["& more", "and more", "plus more", "and much more",
                   "to grow your business", "to boost your results",
                   "for campaigns and strategy planning",
                   "to optimize your strategy"]
IF any banned_ending matches last_words:
  FAIL → regenerate with explicit instruction to end with specific page items

banned_phrases = ["comprehensive guide", "in-depth analysis", "expert recommendations",
                  "actionable tips", "best practices", "everything you need to know",
                  "key strategies", "practical examples", "key insights"]
IF any banned_phrase IN improved_text:
  FAIL → regenerate
```

### 9.4 — Sentence Length Check
```
FOR each sentence in entire report:
  word_count = len(sentence.split())
  IF word_count > 25:
    FAIL → split sentence or rewrite
```

### 9.5 — Schema Mention Count
```
schema_mentions = count sentences referencing "structured data" finding or "0%" schema
IF schema_mentions > 4:
  DELETE mentions in order: (1) summary paragraph, (2) "What this means" box, (3) Quick Win description
  until count = 4
```

### 9.6 — Cover Vertical Centering
```
content_height = measure(logo_top to tended_app_bottom)
available_height = page_height - footer_height
top_padding = (available_height - content_height) / 2
SET content_block.top_margin = top_padding
```

### 9.7 — Number Consistency
```
COLLECT all instances of: health_score, total_posts, issue_count, rec_count,
  orphan_count, thin_count, cann_pair_count, cann_post_count
FOR each metric:
  IF not all instances are identical:
    FAIL → correct to database value
```

### 9.8 — Double-Replacement Detection
```
After the terminology find-and-replace runs, scan for "structured data (structured data)". If found, delete the parenthetical leaving just "structured data."
```