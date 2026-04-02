import Link from 'next/link';

export const metadata = {
  title: 'Privacy Policy — Tended',
  description: 'Privacy Policy for Tended Content Ecosystem Intelligence Platform',
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-[#0a0f1a] text-[#e2e8f0]">
      <nav className="border-b border-[#1e293b] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-lg font-bold tracking-widest text-[#3b82f6]">TENDED</Link>
        <Link href="/login" className="text-sm text-[#64748b] hover:text-[#94a3b8] transition-colors">Sign in</Link>
      </nav>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-[#64748b] text-sm mb-10">Last updated: March 2026</p>

        {[
          {
            title: '1. What We Collect',
            body: 'We collect: (a) Account data — your email address and encrypted password when you register; (b) Content data — publicly accessible HTML from URLs you submit for analysis; (c) Usage data — pages visited, features used, and error logs to improve the Service; (d) Payment data — processed by Stripe; we do not store card details.',
          },
          {
            title: '2. What We Do Not Collect',
            body: 'We do not collect personal data from visitors to your website. We do not collect private or password-protected content. We do not sell your data to third parties. We do not use your content to train AI models.',
          },
          {
            title: '3. How We Use Your Data',
            body: 'Content data is used exclusively to generate your site analysis and recommendations. Account data is used to authenticate your session and communicate service updates. Usage data is used to improve the Service and diagnose errors.',
          },
          {
            title: '4. Data Storage and Security',
            body: 'Data is stored in Supabase (PostgreSQL) hosted on AWS infrastructure in Canada. Content embeddings are stored using pgvector. All connections use TLS. We follow industry-standard security practices.',
          },
          {
            title: '5. Data Retention',
            body: 'Content analysis data is retained for the lifetime of your account. If you delete your account, all associated data is deleted within 30 days. You may request data deletion at any time by emailing privacy@usetended.io.',
          },
          {
            title: '6. Third-Party Services',
            body: 'We use: Supabase (database and authentication), Stripe (payment processing), Resend (transactional email), and OpenAI (content embeddings). Each has its own privacy policy. We share only the minimum data required for each service to function.',
          },
          {
            title: '7. Cookies',
            body: 'We use session cookies for authentication. We do not use tracking cookies or advertising cookies. We do not use third-party analytics that track individual users.',
          },
          {
            title: '8. Your Rights (GDPR)',
            body: 'If you are in the EU/EEA, you have the right to: access your personal data, correct inaccurate data, request deletion, object to processing, and data portability. Contact privacy@usetended.io to exercise these rights.',
          },
          {
            title: '9. Changes',
            body: 'We will notify you via email of material changes to this policy at least 30 days before they take effect.',
          },
          {
            title: '10. Contact',
            body: 'Data controller: Tended. For privacy questions: privacy@usetended.io',
          },
        ].map(({ title, body }) => (
          <div key={title} className="mb-8">
            <h2 className="text-lg font-semibold text-[#e2e8f0] mb-2">{title}</h2>
            <p className="text-[#94a3b8] leading-relaxed">{body}</p>
          </div>
        ))}

        <div className="mt-12 pt-8 border-t border-[#1e293b] flex gap-6 text-sm text-[#64748b]">
          <Link href="/terms" className="hover:text-[#94a3b8] transition-colors">Terms of Service</Link>
          <Link href="/" className="hover:text-[#94a3b8] transition-colors">Home</Link>
        </div>
      </div>
    </div>
  );
}
