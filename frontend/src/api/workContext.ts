/** One navigation vocabulary for reading, evidence, learning and saved work. */
export const contextKeys = ['project','paper','page','ref','focus','session','lesson','step','activity','unit','document_id','document_version','returnTo'] as const;
export type WorkContext = Partial<Record<typeof contextKeys[number], string>>;
export function safeReturnTo(value: string | null | undefined): string | undefined {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\x00-\x20\x7f]/.test(value)) return;
  try {
    const url = new URL(value, 'https://paperstride.local'), path = decodeURIComponent(url.pathname);
    if(url.origin !== 'https://paperstride.local' || path.startsWith('//') || /[\\\x00-\x20\x7f]/.test(path))return;
    if(path!=='/'&&!/^\/(research|papers|learn|practice|cases|explore|graph|manage|workflow|tasks|actions|roadmap)(\/|$)/.test(path))return;
    url.searchParams.delete('returnTo');
    return url.pathname + url.search + url.hash;
  } catch { return; }
}
export function readWorkContext(params: URLSearchParams): WorkContext {
  return Object.fromEntries(contextKeys.flatMap(key => {
    const value = params.get(key);
    return value && (key !== 'returnTo' || safeReturnTo(value)) ? [[key,value]] : [];
  }));
}
export function contextLink(path: string, current: URLSearchParams, overrides: Record<string,string|number|null|undefined> = {}): string {
  const target = new URL(path, 'https://paperstride.local');
  const next = new URLSearchParams(readWorkContext(current));
  target.searchParams.forEach((value,key) => next.set(key,value));
  Object.entries(overrides).forEach(([key,value]) => value == null ? next.delete(key) : next.set(key,String(value)));
  if(next.has('returnTo')){const back=safeReturnTo(next.get('returnTo'));back?next.set('returnTo',back):next.delete('returnTo');}
  return target.pathname + (next.size ? '?' + next.toString() : '') + target.hash;
}
export interface SourceSelection { paper_uid: string; document_id?: string; document_version?: string; page?: number; quote: string; kind?: 'note'|'question'; }
export function workspaceCacheKey(accountId: string | undefined, suffix: string) { return `paperstride:${accountId || 'local'}:${suffix}`; }
