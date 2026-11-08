"use client";

import { useState } from 'react';
import type { InsightDetail, InsightAssignees, InsightAssignment } from '@/lib/insights';
import { useLanguage } from '@/lib/i18n/LanguageContext';

export function InsightAssignmentForm({ insight, assignees, save, busy, allowOwnReview = false }: { insight: InsightDetail; assignees: InsightAssignees; save: (body: InsightAssignment) => void; busy: boolean; allowOwnReview?: boolean }) {
  const { t } = useLanguage();
  const [owner, setOwner] = useState(insight.owner_id == null ? '' : String(insight.owner_id));
  const [reviewer, setReviewer] = useState(insight.reviewer_id == null ? '' : String(insight.reviewer_id));
  const [priority, setPriority] = useState(insight.priority ?? 1);
  const [due, setDue] = useState(insight.due_at ? new Date(new Date(insight.due_at).getTime() - new Date(insight.due_at).getTimezoneOffset() * 60000).toISOString().slice(0,16) : '');
  const select = 'mt-1 block w-full rounded border border-ds-zinc-500 bg-card p-2';
  return <form className="grid gap-3 rounded border border-ds-zinc-500/30 p-3 text-xs sm:grid-cols-2" onSubmit={event => { event.preventDefault(); save({ expected_revision: insight.revision, expected_work_revision: insight.work_revision, owner_id: owner ? Number(owner) : null, reviewer_id: reviewer ? Number(reviewer) : null, priority, due_at: due ? new Date(due).toISOString() : null }); }}>
    <label>{t('insightWork.owner')}<select disabled={!assignees.can_manage} value={owner} onChange={e => setOwner(e.target.value)} className={select}><option value="">{t('insightWork.unassigned')}</option>{assignees.items.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
    <label>{t('insightWork.reviewer')}<select value={reviewer} onChange={e => setReviewer(e.target.value)} className={select}><option value="">{t('insightWork.unassigned')}</option>{assignees.items.filter(person => person.can_review && (allowOwnReview || person.id !== insight.created_by_id)).map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
    <label>{t('insightWork.priorityLabel')}<select disabled={!assignees.can_manage} value={priority} onChange={e => setPriority(Number(e.target.value))} className={select}>{[3,2,1,0].map(p => <option key={p} value={p}>{t(`insightWork.priority.${p}`)}</option>)}</select></label>
    <label>{t('insightWork.due')}<input disabled={!assignees.can_manage} type="datetime-local" value={due} onChange={e => setDue(e.target.value)} className={select} /></label>
    {assignees.truncated && <p>{t('insightWork.narrowSearch')}</p>}
    <button disabled={busy} className="rounded bg-ds-indigo-600 p-2 text-ds-white disabled:opacity-50">{t(assignees.can_manage ? 'insightWork.saveAssignment' : 'insightWork.requestReview')}</button>
  </form>;
}
