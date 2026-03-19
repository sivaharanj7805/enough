/**
 * Centralized microcopy system.
 *
 * All user-facing strings live here so voice, tone, and terminology stay
 * consistent across the app. Edit copy in one place, not 30 components.
 *
 * Naming convention: SECTION.key — e.g. copy.today.heroTitle
 */

// ─── Today Page ──────────────────────────────────

export const today = {
  heroLabel: 'Content Health',
  heroLabelDemo: 'Content Health \u00B7 Demo',
  urgentIssues: (count: number) =>
    `${count} urgent issue${count === 1 ? '' : 's'}`,
  noUrgent: (total: number) =>
    `${total} actions available \u00B7 no critical issues`,
  totalActions: (count: number) =>
    `${count} total action${count === 1 ? '' : 's'}`,
  priorityHeading: 'Your top priorities',
  allCaughtUp: 'All caught up',
  allCaughtUpSub: 'No pending high-priority actions right now.',
  viewAll: (count: number) => `All ${count} actions`,
} as const;

// ─── Pipeline Progress ──────────────────────────

export const pipeline = {
  stages: {
    crawling: {
      label: 'Crawling posts',
      description: 'Discovering and downloading every page on your blog.',
    },
    embedding: {
      label: 'Understanding content',
      description: 'Reading each post and creating a semantic fingerprint.',
    },
    analyzing: {
      label: 'Running analysis',
      description: 'Scoring health, detecting problems, and finding overlap.',
    },
    clustering: {
      label: 'Clustering topics',
      description: 'Grouping posts by topic similarity to find your content pillars.',
    },
    completed: {
      label: 'Building recommendations',
      description: 'Prioritizing what to fix first for maximum traffic impact.',
    },
  },
  discovering: 'Discovering posts\u2026',
  found: (count: number, processed: number) =>
    `Found ${count} posts \u2014 processing ${processed} so far`,
  canClose: 'You can close this tab \u2014 we\u2019ll finish in the background. Come back in ~20 min.',
  timeEstimate: 'Takes 10\u201340 min depending on blog size. We\u2019ll analyze every post.',
} as const;

// ─── Setup Checklist ────────────────────────────

export const setup = {
  heading: 'Get the most from Enough',
  steps: {
    connectBlog: {
      label: 'Connect your blog',
      description: 'We need your sitemap or WordPress URL to start analyzing.',
    },
    waitForAnalysis: {
      label: 'Wait for analysis',
      description: 'Our pipeline crawls, embeds, clusters, and scores your content.',
    },
    connectGA4: {
      label: 'Connect Google Analytics',
      description: 'Traffic data unlocks decay detection and health scoring.',
    },
    connectGSC: {
      label: 'Connect Search Console',
      description: 'Query data powers cannibalization detection and ranking analysis.',
    },
    reviewPriorities: {
      label: 'Review your top priority',
      description: 'Take your first action \u2014 the highest-impact recommendation.',
    },
  },
} as const;

// ─── Empty States ───────────────────────────────

export const empty = {
  noSite: {
    title: 'No blog connected yet',
    description:
      'Connect your blog to see your content health score, find cannibalization, and get prioritized recommendations.',
    action: 'Analyze my blog',
  },
  noClusters: {
    title: 'No topic clusters yet',
    description:
      'Run the analysis pipeline to discover how your content is organized by topic.',
    action: 'Start analysis',
  },
  noRecommendations: {
    title: 'No recommendations',
    description:
      'Either everything looks good, or the analysis pipeline hasn\u2019t run yet.',
  },
  noProblems: {
    title: 'No issues detected',
    description: 'Your content is looking healthy. We\u2019ll alert you if anything changes.',
  },
  noCannibalization: {
    title: 'No cannibalization detected',
    description:
      'None of your posts are competing against each other for the same queries. Nice work.',
  },
  noConsolidation: {
    title: 'No consolidation opportunities',
    description:
      'No swamp clusters detected \u2014 your content isn\u2019t over-bloated in any topic area.',
  },
} as const;

// ─── Severity Labels ────────────────────────────

export const severity = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
} as const;

// ─── Recommendation Types ───────────────────────

export const recType: Record<string, string> = {
  merge: 'Merge posts',
  expand: 'Expand content',
  interlink: 'Add internal links',
  add_schema: 'Add schema markup',
  improve_ai_citability: 'Boost AI citability',
  strengthen_eeat: 'Strengthen E-E-A-T',
  improve_ai_structure: 'Improve AI structure',
  rewrite: 'Rewrite post',
  redirect: 'Set up redirect',
  seo_fix: 'SEO fix',
};

// ─── Ecosystem States ───────────────────────────

export const ecosystemState: Record<string, { label: string; description: string }> = {
  forest: {
    label: 'Forest',
    description: 'Healthy cluster with strong pillar content and good internal linking.',
  },
  meadow: {
    label: 'Meadow',
    description: 'Growing cluster with room for expansion and more supporting content.',
  },
  seedbed: {
    label: 'Seedbed',
    description: 'New cluster with few posts \u2014 needs nurturing to grow.',
  },
  desert: {
    label: 'Desert',
    description: 'Declining cluster with decaying traffic and stale content.',
  },
  swamp: {
    label: 'Swamp',
    description: 'Over-bloated cluster with cannibalization \u2014 needs consolidation.',
  },
};

// ─── Error Messages ─────────────────────────────

export const errors = {
  generic: 'Something went wrong. Please try again.',
  network: 'Network error \u2014 check your connection and try again.',
  unauthorized: 'Your session has expired. Please sign in again.',
  notFound: 'The page you\u2019re looking for doesn\u2019t exist.',
  pipelineFailed: 'Pipeline failed. Check that your blog has a sitemap.xml.',
  pipelineTimeout:
    'Analysis is taking longer than expected. Check back in a few minutes.',
} as const;

// ─── Onboarding ─────────────────────────────────

export const onboarding = {
  title: 'Connect your blog',
  subtitle: 'We\u2019ll analyze every post and find what to fix',
  urlLabel: 'Blog URL or sitemap URL',
  urlPlaceholder: 'https://yourblog.com/sitemap.xml',
  nameLabel: 'Site name',
  namePlaceholder: 'My Blog',
  filterLabel: 'URL path filter',
  filterPlaceholder: '/blog/, /resources/ (comma-separated)',
  filterHelp: 'Only analyze URLs containing these paths. Leave blank to analyze everything.',
  submitButton: 'Analyze my blog',
  readOnly: 'Read-only \u2014 Enough never modifies your content or blog.',
  analyzing: 'Analyzing your blog',
  complete: 'Analysis complete',
} as const;

// ─── Weekly Email ───────────────────────────────

export const weeklyEmail = {
  subject: (siteName: string) => `Your Ecosystem This Week \u2014 ${siteName}`,
  quickWin: (label: string, count: number) =>
    `Consolidate ${label} \u2014 ${count} posts could become 1 strong pillar.`,
  topPriority: (title: string) => `Top priority this week: ${title}`,
} as const;

// ─── Misc ───────────────────────────────────────

export const misc = {
  demoBanner:
    'Showing Close.com \u2014 958 posts analyzed. Connect your blog to see your own data.',
  analyzeCta: 'Analyze my blog \u2192',
  readOnlyBadge: 'Read-only \u2014 we never modify your content',
} as const;
