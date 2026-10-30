import '@testing-library/jest-dom/vitest';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, useSearchParams} from 'react-router-dom';
import {ConfigProvider} from 'antd';
import {beforeEach, expect, test, vi} from 'vitest';
import {apiGet, apiPost} from '../api/client';
import EvidenceMatrix from '../components/workbench/EvidenceMatrix';
import {InspectorContext} from '../components/workspace/InspectorContext';

vi.mock('../api/client', () => ({apiGet: vi.fn(), apiPost: vi.fn()}));
vi.mock('../components/workbench/SyncedDraft', () => ({default: () => null}));

const matrix = {
  version: 1,
  data: [{id: 'method', title: 'Method', rule: 'method', hidden: false}],
  papers: [{uid: 'paper-one', title: 'Paper one'}],
  cells: [{paper_uid: 'paper-one', column_id: 'method', version: 4,
    data: {content: 'Original method summary', origin: 'user_input', finding: 'reported', review: 'pending'}}],
  candidates: [{paper_uid: 'paper-one', column_id: 'method', version: 1, fingerprint: 'candidate-one',
    data: {content: 'Candidate method from the source', origin: 'literature_report', finding: 'reported',
      review: 'pending', document_id: 'doc-one', document_version: 'sha256:one', passage_id: 'passage-one', page: 3}}],
};

function SourceNavigation() {
  const [params, setParams] = useSearchParams();
  const show = (panel: string) => setParams(old => {const next = new URLSearchParams(old); next.set('panel', panel); return next;});
  return <><output data-testid="panel">{params.get('panel')}</output>
    <button onClick={() => show('evidence')}>Finish opening the source</button>
    <button onClick={() => show('closed')}>Close the source panel</button></>;
}

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks();
  vi.mocked(apiGet).mockImplementation(async (path: string) => path.endsWith('/history') ? {items: []} as any : matrix as any);
  vi.mocked(apiPost).mockResolvedValue({} as any);
});

test('the editor waits for delayed source navigation before restoring an unsaved cell draft', async () => {
  // Inspect deliberately does not update the router: the real navigation can arrive later.
  const inspect = vi.fn();
  render(<ConfigProvider theme={{token: {motion: false}}}><MemoryRouter initialEntries={['/research/project-one?tab=compare&panel=closed']}>
    <InspectorContext.Provider value={{inspect, openResource: vi.fn(), refresh: vi.fn()}}>
      <SourceNavigation/><EvidenceMatrix projectId="project-one"/>
    </InspectorContext.Provider>
  </MemoryRouter></ConfigProvider>);

  fireEvent.click((await screen.findByText('Original method summary')).closest('button')!);
  const body = await screen.findByLabelText('单元格内容');
  fireEvent.change(body, {target: {value: 'My unsaved comparison and open question.'}});
  fireEvent.click(screen.getByText('查看来源').closest('button')!);

  expect(inspect).toHaveBeenCalledWith(expect.objectContaining({
    kind: 'passage', id: 'passage-one', document_id: 'doc-one', document_version: 'sha256:one', page: 3,
  }));
  expect(screen.getByTestId('panel')).toHaveTextContent('closed');
  await waitFor(() => expect(body).not.toBeVisible());
  expect(apiPost).not.toHaveBeenCalled();

  fireEvent.click(screen.getByText('Finish opening the source'));
  expect(screen.getByTestId('panel')).toHaveTextContent('evidence');
  expect(body).not.toBeVisible();

  fireEvent.click(screen.getByText('Close the source panel'));
  await waitFor(() => expect(screen.getByLabelText('单元格内容')).toBeVisible());
  expect(screen.getByLabelText('单元格内容')).toHaveValue('My unsaved comparison and open question.');
  fireEvent.click(screen.getByText('保存修改').closest('button')!);
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/workbench/projects/project-one/matrix/cells', expect.objectContaining({
    paper_uid: 'paper-one', column_id: 'method', version: 4,
    content: 'My unsaved comparison and open question.', review: 'pending',
  })));
});
