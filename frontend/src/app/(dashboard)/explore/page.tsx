'use client';

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useSite } from '@/lib/hooks/useSite';
import { Layers, Network, CheckSquare, FileText, Map, Wrench } from 'lucide-react';
import { clsx } from 'clsx';

// Lazy-import the existing page content (reuse all existing components)
import dynamic from 'next/dynamic';

const ClusterList     = dynamic(() => import('@/components/explore/ClusterTab'), { ssr: false });
const RecsTab         = dynamic(() => import('@/components/explore/RecsTab'), { ssr: false });
const CannTab         = dynamic(() => import('@/components/explore/CannTab'), { ssr: false });
const PostsTab        = dynamic(() => import('@/components/explore/PostsTab'), { ssr: false });
const LandscapeTab    = dynamic(() => import('@/components/explore/LandscapeTab'), { ssr: false });
const ConsolidationTab = dynamic(() => import('@/components/explore/ConsolidationTab'), { ssr: false });

const TABS = [
  { id: 'clusters',      label: 'Clusters',        icon: Layers },
  { id: 'recommendations', label: 'Actions',       icon: CheckSquare },
  { id: 'cannibalization', label: 'Cannibalization', icon: Network },
  { id: 'posts',         label: 'Posts',            icon: FileText },
  { id: 'landscape',     label: 'Landscape',        icon: Map },
  { id: 'consolidation', label: 'Consolidation',    icon: Wrench },
] as const;

type TabId = typeof TABS[number]['id'];

export default function ExplorePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { currentSite } = useSite();

  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) ?? 'clusters'
  );

  useEffect(() => {
    const t = searchParams.get('tab') as TabId | null;
    if (t && TABS.some(tab => tab.id === t)) {
      setActiveTab(t);
    }
  }, [searchParams]);

  function setTab(id: TabId) {
    setActiveTab(id);
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', id);
    router.replace(`/explore?${params.toString()}`, { scroll: false });
  }

  if (!currentSite) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-[#64748b]">Select a site to explore.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-[#1e293b] overflow-x-auto pb-0">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === id
                ? 'border-[#22c55e] text-[#e2e8f0]'
                : 'border-transparent text-[#64748b] hover:text-[#94a3b8]'
            )}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'clusters'       && <ClusterList />}
        {activeTab === 'recommendations' && <RecsTab />}
        {activeTab === 'cannibalization' && <CannTab />}
        {activeTab === 'posts'           && <PostsTab />}
        {activeTab === 'landscape'       && <LandscapeTab />}
        {activeTab === 'consolidation'   && <ConsolidationTab />}
      </div>
    </div>
  );
}
