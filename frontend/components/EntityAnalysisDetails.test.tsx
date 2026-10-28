import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import type { CodeEntity } from '@/types/domain';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { api } from '@/app/services/api';
import { axiosResponse } from '@/test/http';
import { EntityAnalysisDetails } from './EntityAnalysisDetails';

vi.mock('@/app/services/api', () => ({ api: { getEntity: vi.fn(), getEntityNeighbors: vi.fn() } }));

type Entity = CodeEntity & { id: number };
const file: Entity = { id: 1, name: 'C.java', type: 'compilation_unit', file_path: 'C.java', start_line: 1, source_id: 7,
  meta: { module: 'app', maven_active_profiles: ['prod'], maven_visibility: ['app', 'api'], maven_runtime_visibility: ['app', 'api', 'impl'], maven_issues: ['External parent missing'] } };
const method: Entity = { id: 2, name: 'use', qualified_name: 'C#use()', type: 'method', file_path: 'C.java', start_line: 5, source_id: 7,
  meta: { return_type: 'String', parameter_types: ['Order'], throws_types: ['IOException'], annotation_details: [{ name: 'Named', source: '@Named("fast")' }],
    return_expressions: [{ expression: 'result', start_line: 12 }], exception_flow: [{ kind: 'catch', exception_types: ['IOException'], start_line: 9 }],
    data_flow_truncated: true, data_flow_omitted: 11,
    data_flow: [{ line: 8, operation: 'assign', target: { name: 'result' }, sources: [{ name: 'order' }], text: 'result = order;' }] } };
const endpoint: Entity = { id: 3, name: '/orders', type: 'endpoint', file_path: 'C.java', start_line: 15, source_id: 7,
  meta: { protocol: 'http', framework: 'spring', http_method: 'GET', path: '/orders', return_type: 'Order', parameters: [{ name: 'id', type: 'long' }] } };
const bean: Entity = { id: 4, name: 'Fast', type: 'class', file_path: 'C.java', start_line: 20, source_id: 7,
  meta: { bean: { names: ['fast'], provided_type: 'api.Port', framework: 'spring', profiles: ['prod'], active: false, activation_unknown: true, primary: true } } };
const all = [file, method, endpoint, bean];
const lite = all.map(({ meta: _meta, ...entity }) => entity);

beforeEach(() => {
  vi.mocked(api.getEntity).mockImplementation(async id => axiosResponse(all.find(entity => entity.id === id)!));
  vi.mocked(api.getEntityNeighbors).mockResolvedValue(axiosResponse({ entity: method, groups: {} }));
});
afterEach(() => vi.resetAllMocks());

function view() {
  const onOpenFile = vi.fn();
  render(<LanguageProvider><EntityAnalysisDetails entity={lite[1]} fileEntity={lite[0]} entities={lite} filePath="C.java" projectId={3} theme="dark" onOpenFile={onOpenFile} /></LanguageProvider>);
  return onOpenFile;
}

it('loads scoped details only after expanding and shows method, Maven and truncation metadata', async () => {
  const onOpenFile = view();
  expect(api.getEntity).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Objektdetails · use'));
  expect(await screen.findByText('Rückgabetyp')).toBeTruthy();
  expect(screen.getByText('String')).toBeTruthy();
  expect(screen.getByText('@Named("fast")')).toBeTruthy();
  expect(screen.getByText('External parent missing')).toBeTruthy();
  expect(screen.getByText(/11 weitere Anweisungen/)).toBeTruthy();
  expect(screen.getByText('result = order;')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'L12' }));
  expect(onOpenFile).toHaveBeenCalledWith('C.java', 12, 7);
  expect(api.getEntity).toHaveBeenCalledWith(2, 3);
  expect(api.getEntity).toHaveBeenCalledWith(1, 3);
});

it('switches to endpoint and bean metadata without claiming unknown activation is active', async () => {
  view();
  fireEvent.click(screen.getByText('Objektdetails · use'));
  await screen.findByText('String');
  fireEvent.change(screen.getByLabelText('Objekt'), { target: { value: '3' } });
  expect(await screen.findByText('GET')).toBeTruthy();
  expect(screen.getByText('/orders', { selector: 'dd' })).toBeTruthy();
  expect(screen.getByText('id: long')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Objekt'), { target: { value: '4' } });
  expect(await screen.findByText(/Aktivierung nicht statisch bestimmbar/)).toBeTruthy();
  expect(screen.queryByText('Im konfigurierten Profil aktiv')).toBeNull();
  expect(screen.getByText('api.Port')).toBeTruthy();
});

it('ignores a late reply for the previously selected object', async () => {
  let resolveOld!: (value: Awaited<ReturnType<typeof api.getEntity>>) => void;
  vi.mocked(api.getEntity).mockImplementation(id => id === 2 ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve(axiosResponse(all.find(entity => entity.id === id)!)));
  view();
  fireEvent.click(screen.getByText('Objektdetails · use'));
  await waitFor(() => expect(api.getEntity).toHaveBeenCalledWith(2, 3));
  fireEvent.change(screen.getByLabelText('Objekt'), { target: { value: '3' } });
  await screen.findByText('GET');
  await act(async () => resolveOld(axiosResponse({ ...method, meta: { return_type: 'OLD_RESULT' } })));
  expect(screen.queryByText('OLD_RESULT')).toBeNull();
  expect(screen.getByText('GET')).toBeTruthy();
});

it('keeps file context visible if the focused entity cannot be loaded', async () => {
  vi.mocked(api.getEntity).mockRejectedValueOnce(new Error('gone'));
  view();
  fireEvent.click(screen.getByText('Objektdetails · use'));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByText('External parent missing')).toBeTruthy();
});

it('opens a derived binding and makes partial relationship loading explicit', async () => {
  vi.mocked(api.getEntityNeighbors).mockResolvedValue(axiosResponse({ entity: method,
    groups: { 'DISPATCHES_TO:out': [{ edge_id: 9, type: 'DISPATCHES_TO', direction: 'out', resolution: 'resolved', dst_name: 'Fast', entity: bean, start_line: 8, end_line: 8 }] },
    page: { 'DISPATCHES_TO:out': { total: 20, has_more: true, next_after: 9 } } }));
  const onOpenFile = view();
  fireEvent.click(screen.getByText('Objektdetails · use'));
  fireEvent.click(await screen.findByRole('button', { name: 'Fast' }));
  expect(onOpenFile).toHaveBeenCalledWith('C.java', 20, 7);
  expect(screen.getByText('Weitere Verbindungen stehen im Referenzen-Menü zur Verfügung.')).toBeTruthy();
});
