import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiMocks, settingsState } = vi.hoisted(() => ({
  apiMocks: { getMcpToolAuditLogs: vi.fn() },
  settingsState: { theme: 'dark' as const, currentUser: { id: 1, username: 'admin', is_admin: true } as { id: number; username: string; is_admin: boolean } },
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsState }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'de',
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}:${Object.values(values).join('/')}` : key,
  }),
}));

import { MCP_AUDIT_PAGE_SIZE, McpAuditLog } from './McpAuditLog';

const entry = (id: number, overrides: Record<string, unknown> = {}) => ({
  id, tool_name: `tool_${id}`, server_name: 'doctus', status: 'success', user_name: 'max',
  duration_ms: 12, arguments: { q: id }, created_at: null, ...overrides,
});
const page = (ids: number[], total: number, offset = 0) => ({
  data: { entries: ids.map((id) => entry(id)), total, offset, limit: MCP_AUDIT_PAGE_SIZE, retention_days: 30 },
});
const range = (start: number, count: number) => Array.from({ length: count }, (_, i) => start - i);

beforeEach(() => {
  settingsState.currentUser = { id: 1, username: 'admin', is_admin: true };
});
afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe('McpAuditLog', () => {
  it('requests only one page of 20 and renders exactly those rows', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValue(page(range(500, 20), 500));
    render(<McpAuditLog />);

    expect(await screen.findAllByTestId('mcp-audit-row')).toHaveLength(20);
    expect(apiMocks.getMcpToolAuditLogs).toHaveBeenCalledWith({ limit: 20, offset: 0 });
    expect(screen.getByTestId('list-pager-range').textContent).toBe('settings.pager.range:1/20/500');
  });

  it('pages forward and back with server-side offsets and never keeps more than one page', async () => {
    apiMocks.getMcpToolAuditLogs
      .mockResolvedValueOnce(page(range(45, 20), 45))
      .mockResolvedValueOnce(page(range(25, 20), 45, 20))
      .mockResolvedValueOnce(page(range(5, 5), 45, 40));
    render(<McpAuditLog />);
    await screen.findAllByTestId('mcp-audit-row');

    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    await waitFor(() => expect(apiMocks.getMcpToolAuditLogs).toHaveBeenLastCalledWith({ limit: 20, offset: 20 }));
    expect(await screen.findByText('tool_25')).toBeTruthy();
    expect(screen.queryByText('tool_45')).toBeNull();
    expect(screen.getAllByTestId('mcp-audit-row')).toHaveLength(20);

    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    await waitFor(() => expect(apiMocks.getMcpToolAuditLogs).toHaveBeenLastCalledWith({ limit: 20, offset: 40 }));
    await waitFor(() => expect(screen.getAllByTestId('mcp-audit-row')).toHaveLength(5));
    expect((screen.getByLabelText('settings.pager.nextPage') as HTMLButtonElement).disabled).toBe(true);
  });

  it('does not jump back to page 1 when the unchanged filter debounce fires after paging', async () => {
    apiMocks.getMcpToolAuditLogs.mockImplementation(async ({ offset }: { offset: number }) =>
      page(range(45 - offset, 20), 45, offset));
    render(<McpAuditLog />);
    await screen.findAllByTestId('mcp-audit-row');
    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    expect(await screen.findByText('tool_25')).toBeTruthy();

    // Der Entprellzeitgeber (300 ms) wurde beim Öffnen gestartet und feuert jetzt, obwohl der Filter unverändert ist.
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 450)); });

    expect(apiMocks.getMcpToolAuditLogs).not.toHaveBeenLastCalledWith({ limit: 20, offset: 0 });
    expect(screen.getByText('tool_25')).toBeTruthy();
    expect(screen.queryByText('tool_45')).toBeNull();
  });

  it('disables the previous button on the first page', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValue(page(range(30, 20), 30));
    render(<McpAuditLog />);
    await screen.findAllByTestId('mcp-audit-row');
    expect((screen.getByLabelText('settings.pager.previousPage') as HTMLButtonElement).disabled).toBe(true);
  });

  it('expands a row on click to show arguments, trace id and error, collapsed by default', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValue({
      data: { entries: [entry(1, { status: 'error', trace_id: 'trace-abc', error_message: 'timeout', project_name: 'Doctus' })], total: 1, offset: 0, limit: 20, retention_days: 30 },
    });
    render(<McpAuditLog />);
    const row = await screen.findByText('tool_1');
    expect(screen.queryByText('trace: trace-abc')).toBeNull();
    expect(screen.getByText('settings.mcpAudit.error')).toBeTruthy();

    fireEvent.click(row);
    expect(screen.getByText('trace: trace-abc')).toBeTruthy();
    expect(screen.getByText('timeout')).toBeTruthy();
    expect(screen.getByText(/"q": 1/)).toBeTruthy();

    fireEvent.click(row);
    expect(screen.queryByText('trace: trace-abc')).toBeNull();
  });

  it('sends the status filter to the server and resets to the first page', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValue(page([3, 2, 1], 3));
    render(<McpAuditLog />);
    await screen.findAllByTestId('mcp-audit-row');

    fireEvent.click(screen.getByText('settings.mcpAudit.filter.error'));
    await waitFor(() => expect(apiMocks.getMcpToolAuditLogs).toHaveBeenLastCalledWith({ limit: 20, offset: 0, status: 'error' }));
  });

  it('debounces the tool filter and shows the filtered empty state', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValueOnce(page([1], 1));
    render(<McpAuditLog />);
    await screen.findAllByTestId('mcp-audit-row');

    apiMocks.getMcpToolAuditLogs.mockResolvedValue({ data: { entries: [], total: 0, offset: 0, limit: 20, retention_days: 30 } });
    fireEvent.change(screen.getByPlaceholderText('settings.mcpAudit.toolFilterPlaceholder'), { target: { value: 'get_call' } });
    expect(apiMocks.getMcpToolAuditLogs).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(apiMocks.getMcpToolAuditLogs).toHaveBeenLastCalledWith({ limit: 20, offset: 0, tool: 'get_call' }));
    expect(await screen.findByText('settings.mcpAudit.emptyFiltered')).toBeTruthy();
  });

  it('shows the empty state when nothing has been audited and hides the pager', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValue({ data: { entries: [], total: 0, offset: 0, limit: 20, retention_days: 30 } });
    render(<McpAuditLog />);
    expect(await screen.findByText('settings.mcpAudit.empty')).toBeTruthy();
    expect(screen.queryByTestId('list-pager-range')).toBeNull();
  });

  it('jumps back when retention pruning removed the current last page', async () => {
    apiMocks.getMcpToolAuditLogs
      .mockResolvedValueOnce(page(range(45, 20), 45))
      .mockResolvedValueOnce(page(range(25, 20), 45, 20))
      .mockResolvedValueOnce(page(range(5, 5), 45, 40))
      .mockResolvedValueOnce({ data: { entries: [], total: 30, offset: 40, limit: 20, retention_days: 30 } })
      .mockResolvedValue(page(range(10, 10), 30, 20));
    render(<McpAuditLog />);
    await screen.findAllByTestId('mcp-audit-row');
    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    await screen.findByText('tool_25');
    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    await waitFor(() => expect(screen.getAllByTestId('mcp-audit-row')).toHaveLength(5));

    fireEvent.click(screen.getByText('settings.mcpAudit.refresh'));
    await waitFor(() => expect(apiMocks.getMcpToolAuditLogs).toHaveBeenLastCalledWith({ limit: 20, offset: 20 }));
  });

  it('refreshes the current page silently every 10 seconds', async () => {
    vi.useFakeTimers();
    apiMocks.getMcpToolAuditLogs.mockResolvedValue(page([1], 1));
    render(<McpAuditLog />);
    await act(async () => { await Promise.resolve(); });
    expect(apiMocks.getMcpToolAuditLogs).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(apiMocks.getMcpToolAuditLogs).toHaveBeenCalledTimes(2);
  });

  it('renders nothing and makes no request for non-admins', () => {
    settingsState.currentUser = { id: 2, username: 'viewer', is_admin: false };
    const { container } = render(<McpAuditLog />);
    expect(container.innerHTML).toBe('');
    expect(apiMocks.getMcpToolAuditLogs).not.toHaveBeenCalled();
  });
});
