import { redirect } from 'next/navigation';

/** Route alias: /recommendations → /actions (GAP-06 fix) */
export default function RecommendationsRedirect() {
  redirect('/actions');
}
