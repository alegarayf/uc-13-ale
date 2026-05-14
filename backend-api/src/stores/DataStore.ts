export interface DataStore {
  /** Human-readable label for health checks */
  readonly label: string;
  ping(): Promise<{ ok: boolean; detail?: string }>;
}
