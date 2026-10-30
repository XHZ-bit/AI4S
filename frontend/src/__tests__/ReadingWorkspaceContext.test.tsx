import '@testing-library/jest-dom/vitest';
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter, useLocation, useSearchParams} from 'react-router-dom';
import {beforeEach, expect, test, vi} from 'vitest';
import {apiGet, apiPost} from '../api/client';
import {getInsights, getResources} from '../api/assistant';
import {contextLink, safeReturnTo, workspaceCacheKey} from '../api/workContext';
import Workspace from '../components/workspace/Workspace';
import {InspectorContext, useInspector} from '../components/workspace/InspectorContext';
import Notebook from '../components/workbench/Notebook';
import SceneSync from '../components/workbench/SceneSync';

vi.mock('../api/client', () => ({apiGet: vi.fn(), apiPost: vi.fn()}));
vi.mock('../api/assistant', () => ({getInsights: vi.fn(), getResources: vi.fn(), explainActions: vi.fn()}));
vi.mock('../components/workbench/SyncedDraft', () => ({default: () => null}));
vi.mock('../components/learning/LearningDashboard', () => ({default: () => null}));
vi.mock('../components/learning/CodePractice', () => ({default: () => null}));
vi.mock('../components/workspace/InteractiveLab', () => ({TensorAnimation: () => null, WindowAnimation: () => null}));
vi.mock('../components/workspace/PdfReader', () => ({default: ({resource, initialPage, quote}: any) =>
  <output data-testid="source-reader">{JSON.stringify({document_id: resource.id, page: initialPage, quote})}</output>}));

const selected = {paper_uid: 'paper-one', document_id: 'doc-one', document_version: 'sha256:version-one', page: 3, quote: 'The policy predicts an action sequence.'};
const tutorResult = {
  id: 'new-session', model: 'fixture',
  source: {paper_uid: 'paper-one', title: 'Paper one', selection: selected, selection_status: 'user_selection'},
  plan: {title: 'One concept', goal: 'Understand the selected text', prerequisites: [], terms: [], quiz: [], exercise: null,
    steps: [{question: 'Why an action sequence?', explanation: 'A short teaching explanation.', example: '', check: ''}]},
};
const note = (id:string, title:string, body:string) => ({id, title, body, kind: 'note', version: 1, project_id: 'project-one', paper_uid: 'paper-one', source_json: '{}'});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}
function SelectionControls() {
  const inspector = useInspector();
  return <><button onClick={() => inspector.openSelection?.(selected, 'tutor')}>Explain selected passage</button>
    <output data-testid="selection">{JSON.stringify(inspector.selection || null)}</output></>;
}
function ReadWorkspace({url='/papers/paper-one?project=project-one&panel=closed'}:{url?:string}) {
  return <MemoryRouter initialEntries={[url]}><LocationProbe/><Workspace scope="paper" id="paper-one"><SelectionControls/><p>Paper body</p></Workspace></MemoryRouter>;
}
function currentParams() { return new URL(screen.getByTestId('location').textContent!, 'https://paperstride.test').searchParams; }

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks();
  Object.defineProperty(window, 'innerWidth', {configurable: true, value: 768});
  vi.mocked(apiGet).mockImplementation(async (path:string) => {
    if (path.startsWith('/api/workbench/projects/')) return {features: {}} as any;
    if (path === '/api/workbench/records' || path === '/api/tutor/sessions') return {items: []} as any;
    if (path.startsWith('/api/tutor/sessions/')) return tutorResult as any;
    return {} as any;
  });
  vi.mocked(apiPost).mockResolvedValue(tutorResult as any);
  vi.mocked(getInsights).mockResolvedValue({actions: [], notice: '', coverage: {}} as any);
  vi.mocked(getResources).mockResolvedValue({items: []} as any);
});

test('return destinations reject external, encoded and non-work routes while removing nested returns', () => {
  for (const unsafe of ['https://outside.test', '//outside.test', '/%2foutside.test', '/%5coutside.test', '/api/auth/logout', '/papers/one\n']) {
    expect(safeReturnTo(unsafe)).toBeUndefined();
  }
  const safe = safeReturnTo('/papers/one?page=3&returnTo=%2Fmanage#selection');
  expect(safe).toBe('/papers/one?page=3#selection');
  expect(workspaceCacheKey('alice', 'selection')).not.toBe(workspaceCacheKey('bob', 'selection'));
});

test('context links preserve the research source and learning position with explicit overrides winning', () => {
  const params = new URLSearchParams({project: 'p', paper: 'paper-one', document_id: 'doc-one', document_version: 'sha256:version-one', page: '3', ref: 'passage:one', session: 's', lesson: 'probability', step: '2', activity: 'visual', unit: 'dp-1'});
  const link = new URL(contextLink('/learn?view=tutor', params, {step: 0, ref: null, returnTo: '/research/p?tab=reading&returnTo=%2Fmanage'}), 'https://paperstride.test');
  expect(link.pathname).toBe('/learn');
  expect(Object.fromEntries(link.searchParams)).toMatchObject({project: 'p', paper: 'paper-one', document_id: 'doc-one', document_version: 'sha256:version-one', page: '3', session: 's', lesson: 'probability', step: '0', activity: 'visual', unit: 'dp-1', view: 'tutor', returnTo: '/research/p?tab=reading'});
  expect(link.searchParams.has('ref')).toBe(false);
  expect(params.get('ref')).toBe('passage:one');
});

test('reading opens with the assistance panel closed and does not request insights or resources', async () => {
  render(<ReadWorkspace/>);
  expect(screen.getByText('Paper body')).toBeVisible();
  await act(async () => {});
  expect(screen.getByRole('button', {name: '展开来源与教练'})).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(getInsights).not.toHaveBeenCalled();
  expect(getResources).not.toHaveBeenCalled();
  expect(apiPost).not.toHaveBeenCalled();
});

test('new selected text clears an older session and sends the exact source context only on request', async () => {
  render(<ReadWorkspace url="/papers/paper-one?project=project-one&panel=closed&session=old-session&step=4"/>);
  fireEvent.click(screen.getByText('Explain selected passage'));
  const submit = await screen.findByRole('button', {name: '拆解并开始辅导'});
  expect(currentParams().has('session')).toBe(false);
  expect(currentParams().has('step')).toBe(false);
  expect(apiPost).not.toHaveBeenCalled();
  fireEvent.click(submit);
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/tutor/sessions', expect.objectContaining({
    paper_uid: 'paper-one', project_id: 'project-one', session_id: undefined,
    source_context: {document_id: 'doc-one', document_version: 'sha256:version-one', page: 3, quote: selected.quote},
  }), expect.any(AbortSignal)));
});

test('a successful tutor session URL update keeps the mobile drawer and selected passage open', async () => {
  render(<ReadWorkspace/>);
  fireEvent.click(screen.getByText('Explain selected passage'));
  fireEvent.click(await screen.findByRole('button', {name: '拆解并开始辅导'}));
  await screen.findByText('One concept');
  await waitFor(() => expect(currentParams().get('session')).toBe('new-session'));
  expect(screen.getByRole('dialog')).toBeVisible();
  expect(screen.getByTestId('selection').textContent).toContain(selected.quote);
  expect(within(screen.getByRole('dialog')).getByText('A short teaching explanation.')).toBeVisible();
});

function SourceControls() {
  const inspector = useInspector();
  return <button onClick={() => inspector.inspect({kind: 'passage', id: 'source-passage'})}>Inspect the same passage</button>;
}

test('reopening the same passage retains its fetched document, page and quote without another fetch', async () => {
  const quote = 'The observation window provides the conditioning context.';
  vi.mocked(apiGet).mockImplementation(async (path: string) => path === '/api/learning/evidence/source-passage'
    ? {text: quote, page: 6, document_id: 'source-doc', paper_uid: 'paper-one'} as any
    : {features: {}} as any);
  vi.mocked(getResources).mockResolvedValue({items: [{
    id: 'source-doc', kind: 'pdf', title: 'Source PDF', origin: 'paper', version: 'sha256:source',
    paper_uid: 'paper-one', document_id: 'source-doc', passages: [],
  }]} as any);
  render(<MemoryRouter initialEntries={['/papers/paper-one?project=project-one&panel=closed']}>
    <Workspace scope="paper" id="paper-one"><SourceControls/></Workspace>
  </MemoryRouter>);

  fireEvent.click(screen.getByRole('button', {name: 'Inspect the same passage'}));
  await waitFor(() => expect(screen.getByTestId('source-reader')).toHaveTextContent(quote));
  expect(JSON.parse(screen.getByTestId('source-reader').textContent!)).toEqual({document_id: 'source-doc', page: 6, quote});
  fireEvent.click(screen.getByRole('button', {name: '关闭阅读辅助'}));
  await waitFor(() => expect(screen.queryByTestId('source-reader')).not.toBeInTheDocument());

  // Same id/kind is intentionally a minimal reference, as when returning to the same matrix candidate.
  fireEvent.click(screen.getByRole('button', {name: 'Inspect the same passage'}));
  await waitFor(() => expect(screen.getByTestId('source-reader')).toBeVisible());
  expect(JSON.parse(screen.getByTestId('source-reader').textContent!)).toEqual({document_id: 'source-doc', page: 6, quote});
  expect(vi.mocked(apiGet).mock.calls.filter(([path]) => path === '/api/learning/evidence/source-passage')).toHaveLength(1);
});

function SwitchRecord() {
  const [,setParams] = useSearchParams();
  return <button onClick={() => setParams({record: 'note-b'})}>Open note B by link</button>;
}
test('a slow note save cannot replace another record opened through a deep link', async () => {
  let finish!:(value:any)=>void;
  const rows = [note('note-a', 'Note A', 'A body'), note('note-b', 'Note B', 'B body')];
  vi.mocked(apiGet).mockResolvedValue({items: rows} as any);
  vi.mocked(apiPost).mockImplementationOnce(() => new Promise(resolve => {finish=resolve;}));
  render(<MemoryRouter initialEntries={['/research/project-one?record=note-a']}><SwitchRecord/><Notebook projectId="project-one"/></MemoryRouter>);
  await screen.findByDisplayValue('A body');
  fireEvent.change(screen.getByLabelText('记录内容'), {target: {value: 'Submitted A'}});
  fireEvent.click(screen.getByRole('button', {name: '保存记录'}));
  await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByText('Open note B by link'));
  await screen.findByDisplayValue('B body');
  await act(async () => finish({...rows[0], version: 2, body: 'Submitted A'}));
  expect(screen.getByLabelText('记录标题')).toHaveValue('Note B');
  expect(screen.getByLabelText('记录内容')).toHaveValue('B body');
});

test('recovering an editor draft decodes its content and saves to the original record with source metadata', async () => {
  const source = {document_id: 'doc-one', document_version: 'sha256:version-one', page: 3, quote: selected.quote};
  const draft = {...note('editor:recovered-note', 'Draft title', JSON.stringify({format: 'paperstride-note-v1', title: 'Recovered title', body: 'Recovered body', kind: 'question', source, paper_uid: 'paper-one', project_id: 'project-one'})), kind: 'draft'};
  vi.mocked(apiGet).mockImplementation(async () => ({items: [{...draft}]} as any));
  vi.mocked(apiPost).mockImplementation(async (_path, body:any) => ({...body, version: 1, source_json: JSON.stringify(source)}) as any);
  render(<MemoryRouter initialEntries={['/research/project-one?record=editor%3Arecovered-note']}><Notebook projectId="project-one"/></MemoryRouter>);
  expect(await screen.findByDisplayValue('Recovered body')).toBeVisible();
  expect(screen.getByLabelText('记录标题')).toHaveValue('Recovered title');
  fireEvent.change(screen.getByLabelText('记录内容'), {target: {value: 'Revised recovered body'}});
  fireEvent.click(screen.getByRole('button', {name: '保存记录'}));
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/workbench/records', expect.objectContaining({id: 'recovered-note', version: 0, kind: 'question', paper_uid: 'paper-one', ...source})));
  await waitFor(() => expect(screen.getByRole('button', {name: '保存记录'})).not.toHaveClass('ant-btn-loading'));
  expect(screen.getByLabelText('记录内容')).toHaveValue('Revised recovered body');
});

test('an explicit evidence link does not restore an older page selection from the same paper', async () => {
  const restore = vi.fn();
  vi.mocked(apiGet).mockResolvedValue({version: 4, data: {view: 'reading', paper: 'paper-one', page: 3, panel: 'tutor', ref: 'passage:old', selection: selected}} as any);
  render(<MemoryRouter initialEntries={['/research/project-one?tab=reading&paper=paper-one&page=7&ref=passage%3Anew&panel=evidence']}><InspectorContext.Provider value={{inspect: vi.fn(), openResource: vi.fn(), refresh: vi.fn(), restoreSelection: restore}}><SceneSync projectId="project-one" view="reading"/><LocationProbe/></InspectorContext.Provider></MemoryRouter>);
  await waitFor(() => expect(apiGet).toHaveBeenCalled());
  expect(currentParams().get('page')).toBe('7');
  expect(currentParams().get('ref')).toBe('passage:new');
  expect(restore).not.toHaveBeenCalled();
});
