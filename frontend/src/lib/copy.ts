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
  priorityHeading: 'Next best actions',
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
  rebuilding: 'Refreshing your data\u2026 Your scores and clusters are being recalculated. This usually takes under 2 minutes.',
  discovering: 'Discovering posts\u2026',
  found: (count: number, processed: number) =>
    `Found ${count} posts \u2014 processing ${processed} so far`,
  canClose: 'You can close this tab \u2014 we\u2019ll finish in the background. Come back in ~20 min.',
  timeEstimate: 'Takes 10\u201340 min depending on blog size. We\u2019ll analyze every post.',
} as const;

// ─── Setup Checklist ────────────────────────────

export const setup = {
  heading: 'Get the most from Tended',
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
    title: 'No competing posts detected',
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
    description: 'Over-bloated cluster with competing posts \u2014 needs consolidation.',
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
  readOnly: 'Read-only \u2014 Tended never modifies your content or blog.',
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

// ─── Empty States (per-page) ───────────────────

export const EMPTY_STATES = {
  today: {
    title: 'Your analysis is running',
    description: 'Results will appear here as the pipeline processes your blog.',
    action: 'View Progress',
  },
  todayComplete: {
    title: 'Your content is in great shape',
    description: "We'll notify you when new issues arise.",
    action: null,
  },
  landscape: {
    title: 'Your content ecosystem is forming',
    description: 'The landscape will render as clusters are detected.',
  },
  clusters: {
    title: 'Clusters appear after analysis',
    description: 'Topics will be grouped automatically once the pipeline completes.',
  },
  posts: {
    title: 'No posts analyzed yet',
    description: 'Posts will appear here once the crawl completes.',
  },
  postNotFound: {
    title: 'Post not found',
    description: 'This post may have been removed or the URL is incorrect.',
  },
  recommendations: {
    title: 'No recommendations yet',
    description: 'Analysis takes about 20 minutes. Recommendations will appear as issues are detected.',
  },
  recommendationsDone: {
    title: 'All recommendations completed. Nice work.',
    description: "We'll generate new recommendations on your next analysis.",
  },
  issuesNone: {
    title: 'No issues found',
    description: 'Your content is in great shape.',
  },
  issuesTab: (type: string) => ({
    title: `No ${type} detected`,
    description: 'Your content looks good here.',
  }),
  cannibalization: {
    title: 'No cannibalization detected',
    description: 'Your posts target distinct topics effectively.',
  },
  consolidation: {
    title: 'No consolidation plans yet',
    description: 'Merge recommendations will appear here.',
  },
  oracle: {
    title: 'Ask Oracle about your content',
    description: 'Get insights about your blog health, clusters, and recommendations.',
  },
  analytics: {
    title: 'Connect your data sources to see analytics',
    description: 'Link Google Search Console and Analytics for traffic insights.',
  },
  impact: {
    title: 'Impact data will be available in 7-14 days',
    description: "We're tracking the effect of your changes.",
  },
  workshop: {
    title: 'No ideas yet',
    description: 'Ask the AI panel a question, or click a cluster to get started.',
  },
  patcher: {
    title: 'Pick a recommendation to fix',
    description: 'Your top-priority items are ready to work on.',
    emptyTitle: 'Nothing to patch',
    emptyDescription: 'All recommendations are either completed or dismissed. Nice work.',
    stepComplete: 'Step complete',
    allDone: 'All steps complete — nice work!',
    allDoneSub: 'Mark this recommendation as done when you are satisfied with the result.',
    aiPanelTitle: 'AI Assistant',
    aiPlaceholder: 'Ask a question about this step...',
  },
} as const;

// ─── Pioneer ────────────────────────────────────

export const pioneer = {
  pageTitle: 'Pioneer',
  pageSubtitle: 'Create new content with your data as co-pilot',
  inputPlaceholder: 'What do you want to write about?',
  inputHint: 'Type your idea and we\u2019ll scan your content for fit, overlap, and opportunities',
  briefingTitle: 'Briefing',
  clusterFit: 'Cluster fit',
  overlapRisk: 'Overlap risk',
  clusterImpact: 'Cluster impact',
  siteKnows: 'What your site knows',
  siteDoesntKnow: 'What your site doesn\u2019t know',
  proceed: 'Proceed',
  rethink: 'Rethink',
  buildTitle: 'Build Canvas',
  sectionTitle: 'Title',
  sectionAngle: 'Angle',
  sectionOutline: 'Outline',
  sectionData: 'Data & Evidence',
  sectionLinks: 'Internal Links',
  sectionPreflight: 'Pre-Flight Check',
  linkTo: 'Link TO this post from',
  linkFrom: 'Link FROM this post to',
  exportBrief: 'Export Brief',
  askPlaceholder: 'Ask something...',
  aiPanelTitle: 'AI Context',
  noClusterData: 'Connect your blog and run the pipeline to see cluster data here.',
} as const;

// ─── Misc ───────────────────────────────────────

export const misc = {
  demoBanner:
    'Showing Close.com \u2014 958 posts analyzed. Connect your blog to see your own data.',
  analyzeCta: 'Analyze my blog \u2192',
  readOnlyBadge: 'Read-only \u2014 we never modify your content',
} as const;

// ─── Health Labels ─────────────────────────────

export const HEALTH_LABELS: Record<string, { label: string; description: string }> = {
  excellent: { label: 'Excellent', description: 'Your content is well-structured and competitive.' },
  good: { label: 'Good', description: 'A few targeted improvements could make a real difference.' },
  needsWork: { label: 'Needs work', description: 'There are clear opportunities to strengthen your content.' },
  significant: { label: 'Significant issues', description: 'Your content is underperforming its potential.' },
  critical: { label: 'Critical', description: 'Major structural problems are limiting your content\'s reach.' },
};

export function getHealthLabel(score: number) {
  if (score >= 80) return HEALTH_LABELS.excellent;
  if (score >= 60) return HEALTH_LABELS.good;
  if (score >= 40) return HEALTH_LABELS.needsWork;
  if (score >= 20) return HEALTH_LABELS.significant;
  return HEALTH_LABELS.critical;
}

// ─── Button Labels ─────────────────────────────

export const BUTTON_LABELS = {
  analyzeMyBlog: 'Analyze My Blog',
  viewFullPlan: 'View Full Plan',
  markAsDone: 'Mark as Done',
  connectGSC: 'Connect Google Search Console',
  connectGA4: 'Connect Google Analytics',
  dismiss: 'Dismiss',
  reAnalyze: 'Re-analyze',
  getAudit: 'Get Your Free Audit',
  subscribe: 'Subscribe & Start Fixing',
};

// ─── Error Messages ────────────────────────────

export const ERROR_MESSAGES = {
  urlUnreachable: "We couldn't reach that URL. Make sure it's publicly accessible and try again.",
  serverError: "Something went wrong on our end. We're looking into it. Try again in a few minutes.",
  tooFewPosts: "Your blog has fewer than 10 posts. Tended works best with 25+ posts.",
  sessionExpired: "Your session has expired. Please log in again.",
  networkOffline: "You're offline. Some features may be unavailable.",
};

// ─── Retention / Today Page ──────────────────────

export const retention = {
  estimatedImpact: (points: number) =>
    `Estimated health impact: +${points} point${points !== 1 ? 's' : ''} when re-analyzed`,
  ga4CtaEnhancedTitle: 'See if your fixes are working',
  ga4CtaEnhanced: (n: number) =>
    `You've completed ${n} recommendation${n !== 1 ? 's' : ''}. Connect Google Analytics to track the real impact of your changes.`,
  ga4CtaConnect: 'Connect Google Analytics',
  diffTitle: 'Re-analysis Complete',
  diffScoreChange: (before: number, after: number, delta: number) =>
    `Score: ${before} \u2192 ${after} (${delta > 0 ? '+' : ''}${delta})`,
  diffImprovements: 'Improvements',
  diffNewIssues: 'New Issues',
  diffDegradations: 'Degradations',
  diffFactorChanges: 'Factor Changes',
  diffDismiss: 'Dismiss',
} as const;

// ─── Free Audit ──────────────────────────────────

export const freeAudit = {
  heading: 'Free Content Audit',
  subheading: 'Get a PDF report with your health score, AI Readiness grade, and top issues — delivered to your inbox.',
  urlLabel: 'Blog URL',
  urlPlaceholder: 'https://yourblog.com',
  urlError: 'Enter a valid URL starting with http:// or https://',
  emailLabel: 'Email',
  emailPlaceholder: 'you@example.com',
  emailError: 'Enter a valid email address',
  submit: 'Generate Free Audit',
  submitting: 'Generating...',
  successHeading: 'Audit started',
  successMessage: (domain: string) =>
    `We're analyzing ${domain} now. Your PDF report will arrive in your inbox in about 20-25 minutes.`,
  rateLimitError: 'You\'ve reached the limit of 3 free audits per day. Try again tomorrow.',
  genericError: 'Something went wrong. Please try again.',
  upgradeCta: 'Want the full picture? Upgrade for complete analysis.',
  upgradeButton: 'View Plans',
} as const;

// ─── Tooltips ──────────────────────────────────

export const TOOLTIPS = {
  healthScore: 'A composite of 6 factors: traffic, rankings, engagement, freshness, content depth, and technical SEO.',
  pillarPost: 'A comprehensive, high-authority post that covers a topic in depth and links to related supporting posts.',
  cannibalization: 'When two or more posts target the same keyword, they compete against each other in search results.',
  cosineSimilarity: 'A measure of how similar two pieces of content are, from 0% (completely different) to 100% (identical).',
  pageRank: 'A score based on how many internal links point to this post, indicating its importance within your site.',
};
