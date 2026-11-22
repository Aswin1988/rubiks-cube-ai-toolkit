import type { Move } from "@/lib/cube";

interface ApiError { code: string; message: string }
interface Envelope<T> { ok: boolean; data: T | null; error: ApiError | null }

export interface ScrambleData { state: string; moves: Move[]; seed: string | number | null }
export interface VerificationData {
  verified: boolean;
  status: string;
  final_state: string | null;
  moves: Move[];
  htm: number;
  qtm: number;
  error: string | null;
}
export interface SolveData {
  success: boolean;
  status: string;
  solver: string;
  elapsed_seconds: number;
  moves: Move[];
  verification: VerificationData;
  error: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function post<T>(path: string, body: object, timeoutMs = 12_000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const envelope = (await response.json()) as Envelope<T>;
    if (!response.ok || !envelope.ok || envelope.data === null) {
      throw new Error(envelope.error?.message ?? `request failed with status ${response.status}`);
    }
    return envelope.data;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("The request timed out. The solver may still be warming up.");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export const cubeApi = {
  scramble: (length = 20) => post<ScrambleData>("/api/scramble", { length }),
  solve: (state: string) => post<SolveData>("/api/solve", { state }, 35_000),
};
