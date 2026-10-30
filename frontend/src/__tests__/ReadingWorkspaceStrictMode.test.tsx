import '@testing-library/jest-dom/vitest';
import {StrictMode} from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {beforeEach, expect, test, vi} from 'vitest';
import {apiGet, apiPost} from '../api/client';
import Notebook from '../components/workbench/Notebook';
import ProjectReading from '../components/workbench/ProjectReading';

vi.mock('../api/client', () => ({apiGet: vi.fn(), apiPost: vi.fn()}));
vi.mock('../components/workbench/SyncedDraft', () => ({default: () => null}));
vi.mock('../pages/PaperDetail', () => ({
  PaperDetailContent: ({paperUid}: {paperUid: string}) => <article aria-label="Current paper">{paperUid}</article>,
}));

const selected = {
  paper_uid: 'paper-one', document_id: 'doc-one', document_version: 'sha256:one',
  page: 3, quote: 'The policy predicts an action sequence.',
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks();
  vi.mocked(apiGet).mockResolvedValue({items: []} as any);
  vi.mocked(apiPost).mockImplementation(async (_path, body: any) => ({...body, version: 1}) as any);
});

test('StrictMode effect replay preserves an initial selected-text draft and its saved source', async () => {
  render(<StrictMode><MemoryRouter initialEntries={['/research/project-one?tab=reading&paper=paper-one']}>
    <Notebook projectId="project-one" paperUid="paper-one" initialDraft={selected} compact/>
  </MemoryRouter></StrictMode>);

  const body = await screen.findByLabelText('记录内容');
  await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText('记录标题')).toHaveValue(selected.quote);
  expect(body).toHaveValue('原文摘录：\n' + selected.quote + '\n\n我的理解：\n');
  expect(screen.queryByText('把研究过程留在这里')).not.toBeInTheDocument();
  expect(apiPost).not.toHaveBeenCalled();

  fireEvent.change(body, {target: {value: 'My explanation of this selected passage.'}});
  fireEvent.click(screen.getByRole('button', {name: '保存记录'}));
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/workbench/records', expect.objectContaining({
    project_id: 'project-one', paper_uid: 'paper-one', document_id: 'doc-one',
    document_version: 'sha256:one', page: 3, quote: selected.quote,
    body: 'My explanation of this selected passage.', kind: 'note',
  })));
  await screen.findByText('已保存到研究记录');
  expect(screen.getByLabelText('记录内容')).toHaveValue('My explanation of this selected passage.');
});

test('switching papers drops the previous source and lesson context before opening the next reader', async () => {
  const stale = new URLSearchParams({
    tab: 'reading', project: 'project-one', paper: 'paper-one', page: '9', ref: 'passage:one',
    focus: 'one', document_id: 'doc-one', document_version: 'sha256:one', session: 'session-one',
    step: '3', lesson: 'probability', activity: 'quiz', unit: 'dp-1',
    returnTo: '/papers/paper-one?page=9', panel: 'tutor',
  });
  const workspace = {papers: [{uid: 'paper-one', title: 'First paper'}, {uid: 'paper-two', title: 'Second paper'}], features: {}};
  render(<MemoryRouter initialEntries={['/research/project-one?' + stale.toString()]}>
    <LocationProbe/><ProjectReading projectId="project-one" workspace={workspace}/>
  </MemoryRouter>);

  fireEvent.mouseDown(screen.getByRole('combobox', {name: '当前论文'}));
  fireEvent.click(await screen.findByText('Second paper', {selector: '.ant-select-item-option-content'}));

  await waitFor(() => expect(screen.getByRole('article', {name: 'Current paper'})).toHaveTextContent('paper-two'));
  const params = new URL(screen.getByTestId('location').textContent!, 'https://paperstride.test').searchParams;
  expect(Object.fromEntries(params)).toEqual({tab: 'reading', project: 'project-one', paper: 'paper-two', panel: 'closed'});
  const separateReader = new URL(screen.getByRole('link', {name: '独立打开'}).getAttribute('href')!, 'https://paperstride.test');
  expect(separateReader.pathname).toBe('/papers/paper-two');
  expect(Object.fromEntries(separateReader.searchParams)).toEqual({project: 'project-one', paper: 'paper-two', tab: 'reading'});
  expect(apiPost).not.toHaveBeenCalled();
});
