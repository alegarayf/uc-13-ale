const AI_BASE = import.meta.env.VITE_AI_API_BASE_URL ?? "http://localhost:8000";

export class AiApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AiApiError";
  }
}

async function parseAiResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string | { msg?: string }[] };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        message = body.detail[0].msg;
      }
    } catch {
      /* non-JSON */
    }
    throw new AiApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

export async function aiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${AI_BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  return parseAiResponse<T>(res);
}

export async function aiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${AI_BASE}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parseAiResponse<T>(res);
}
