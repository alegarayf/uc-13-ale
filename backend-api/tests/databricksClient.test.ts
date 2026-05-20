import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createDatabricksClient,
  resetSharedDatabricksClient,
} from "../src/db/databricksClient.js";

const mockExecuteStatement = vi.fn();
const mockFetchAll = vi.fn();
const mockClose = vi.fn();
const mockOpenSession = vi.fn();
const mockConnect = vi.fn();

vi.mock("@databricks/sql", () => ({
  DBSQLClient: vi.fn().mockImplementation(() => ({
    connect: mockConnect,
  })),
}));

describe("createDatabricksClient", () => {
  afterEach(() => {
    resetSharedDatabricksClient();
    vi.clearAllMocks();
  });

  const cfg = {
    serverHostname: "adb.example.net",
    httpPath: "/sql/1.0/warehouses/abc",
    token: "token",
    catalog: "cat",
    schema: "garden",
  };

  it("throws when env incomplete on query", async () => {
    const client = createDatabricksClient({
      ...cfg,
      token: "",
    });
    await expect(client.query("SELECT 1")).rejects.toThrow(/DATABRICKS_TOKEN/);
  });

  it("runs parameterized queries through session", async () => {
    mockFetchAll.mockResolvedValue([{ id: 1 }]);
    mockClose.mockResolvedValue(undefined);
    mockExecuteStatement.mockResolvedValue({
      fetchAll: mockFetchAll,
      close: mockClose,
    });
    mockOpenSession.mockResolvedValue({
      executeStatement: mockExecuteStatement,
      close: mockClose,
    });
    mockConnect.mockResolvedValue({
      openSession: mockOpenSession,
      close: mockClose,
    });

    const client = createDatabricksClient(cfg);
    await client.ping();
    const rows = await client.query("SELECT :id AS id", { id: 1 });

    expect(rows).toEqual([{ id: 1 }]);
    expect(mockExecuteStatement).toHaveBeenCalledWith(
      "SELECT :id AS id",
      expect.objectContaining({ namedParameters: { id: 1 } }),
    );
    await client.close();
    expect(mockClose).toHaveBeenCalled();
  });
});
