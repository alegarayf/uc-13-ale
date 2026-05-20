/** ISO-8601 timestamp string in JSON request/response payloads. */
export type ApiTimestamp = string;

export interface BaseApiModelFields {
  id: number;
  created_at: ApiTimestamp;
  updated_at: ApiTimestamp;
  last_updated_by: string | null;
}

/**
 * Base model for API entities. All persisted resources include identity and audit fields.
 */
export abstract class BaseApiModel implements BaseApiModelFields {
  readonly id: number;
  readonly created_at: ApiTimestamp;
  readonly updated_at: ApiTimestamp;
  readonly last_updated_by: string | null;

  constructor(fields: BaseApiModelFields) {
    this.id = fields.id;
    this.created_at = fields.created_at;
    this.updated_at = fields.updated_at;
    this.last_updated_by = fields.last_updated_by;
  }
}
