import type {WorkspaceView} from '../../api/knowledge';

export interface WorkspaceResume {
  projectId: string;
  title: string;
  url: string;
  view: WorkspaceView;
  question: string;
  nodeId?: string;
  nodeLabel?: string;
  nodeVersion?: number;
  sourceId?: string;
  sourceTitle?: string;
  sourceVersion?: string;
  judgmentSourceId?: string;
  judgmentSourceVersion?: string;
  page?: string;
  line?: string;
  unresolvedQuestions?: string;
}

export const resumeKey = (accountId: string | undefined, projectId: string) =>
  `paperstride:${accountId || 'local'}:task:${projectId}`;

export function resumeLocation(location: string, depth = 0): string {
  const [pathname, query = ''] = location.split('?');
  const params = new URLSearchParams(query);
  params.delete('quote');
  if (depth < 2) {
    for (const field of ['returnTo', 'graphFrom', 'routeFrom']) {
      const nested = params.get(field);
      if (nested?.startsWith('/')) params.set(field, resumeLocation(nested, depth + 1));
    }
  } else {
    params.delete('returnTo'); params.delete('graphFrom'); params.delete('routeFrom');
  }
  return pathname + (params.size ? '?' + params : '');
}

export function readWorkspaceResume(accountId: string | undefined, projectId: string): WorkspaceResume | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(resumeKey(accountId, projectId)) || 'null');
    if (!value || value.projectId !== projectId || typeof value.url !== 'string') return;
    const expected = '/research/' + encodeURIComponent(projectId);
    if (value.url.split('?')[0] !== expected) return;
    if (!['graph', 'reading', 'learning', 'compare', 'practice', 'materials', 'route'].includes(value.view)) return;
    return value;
  } catch { return; }
}

export function writeWorkspaceResume(accountId: string | undefined, value: WorkspaceResume): boolean {
  try {
    localStorage.setItem(resumeKey(accountId, value.projectId), JSON.stringify({...value, url: resumeLocation(value.url)}));
    return true;
  } catch { return false; }
}

export function resumeDescription(value: WorkspaceResume): string {
  const position = value.page ? `第 ${value.page} 页` : value.line ? `第 ${value.line} 行` : '';
  return [value.sourceTitle, position, value.nodeLabel].filter(Boolean).join(' · ') || value.title;
}
