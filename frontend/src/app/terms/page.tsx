import Link from 'next/link';

export const metadata = {
  title: 'Terms of Service — Tended',
  description: 'Terms of Service for Tended Content Ecosystem Intelligence Platform',
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-[#0a0f1a] text-[#e2e8f0]">
      <nav className="border-b border-[#1e293b] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-lg font-bold tracking-widest text-[#3b82f6]">TENDED</Link>
        <Link href="/login" className="text-sm text-[#64748b] hover:text-[#94a3b8] transition-colors">Sign in</Link>
      </nav>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <h1 className="text-3xl font-bold mb-2">Terms of Service</h1>
        <p className="text-[#64748b] text-sm mb-10">Last updated: March 2026</p>

        {[
          { title: '1. Acceptance of Terms', body: 'By accessing or using Tended ("the Service"), you agree to be bound by these Terms of Service. If you do not agree, do not use the Service.' },
          { title: '2. Description of Service', body: 'Tended is a content intelligence platform that analyses publicly accessible blog content and provides recommendations to improve content performance. The Service is read-only — it does not modify, publish, or delete any content on your website.' },
          { title: '3. Eligibility', body: 'You must be at least 18 years old and have the legal authority to enter into these terms on behalf of yourself or your organisation.' },
          { title: '4. User Accounts', body: 'You are responsible for maintaining the confidentiality of your account credentials. You are responsible for all activity that occurs under your account. Notify us immediately of any unauthorised access.' },
          { title: '5. Acceptable Use', body: 'You agree not to: (a) use the Service to analyse websites you do not own or have permission to analyse; (b) attempt to reverse engineer or disrupt the Service; (c) resell or sublicense access to the Service; (d) use the Service in any way that violates applicable law.' },
          { title: '6. Data and Privacy', body: 'We collect and store publicly accessible content from URLs you provide. We do not collect personal data from your website visitors. See our Privacy Policy for full details on data handling.' },
          { title: '7. Payment and Billing', body: 'Paid plans are billed monthly. Cancellations take effect at the end of the current billing period. Refunds are available within 7 days of initial purchase if the Service has not performed a site analysis. No refunds after analysis is complete.' },
          { title: '8. Intellectual Property', body: 'The Service, including all software, algorithms, and content, is owned by Tended. Your content remains yours — we claim no ownership over content we analyse.' },
          { title: '9. Disclaimer of Warranties', body: 'The Service is provided "as is" without warranty of any kind. We do not guarantee that recommendations will improve search rankings, traffic, or any other metric. SEO results depend on many factors outside our control.' },
          { title: '10. Limitation of Liability', body: 'To the maximum extent permitted by law, Tended shall not be liable for any indirect, incidental, or consequential damages arising from your use of the Service.' },
          { title: '11. Changes to Terms', body: 'We may update these terms from time to time. Continued use of the Service after changes constitutes acceptance of the new terms. We will notify users of material changes via email.' },
          { title: '12. Contact', body: 'For questions about these terms, contact us at legal@usetended.io' },
        ].map(({ title, body }) => (
          <div key={title} className="mb-8">
            <h2 className="text-lg font-semibold text-[#e2e8f0] mb-2">{title}</h2>
            <p className="text-[#94a3b8] leading-relaxed">{body}</p>
          </div>
        ))}

        <div className="mt-12 pt-8 border-t border-[#1e293b] flex gap-6 text-sm text-[#64748b]">
          <Link href="/privacy" className="hover:text-[#94a3b8] transition-colors">Privacy Policy</Link>
          <Link href="/" className="hover:text-[#94a3b8] transition-colors">Home</Link>
        </div>
      </div>
    </div>
  );
}
