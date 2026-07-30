export interface ErrorDescription {
  message: string;
  retryable: boolean;
  code?: string;
}

/** Normalise an unknown thrown value into a structured, model-friendly description. */
export function describeError(err: unknown): ErrorDescription {
  if (err instanceof Error) {
    const e = err as Error & { code?: string; retryable?: boolean; is_retryable?: boolean };
    const out: ErrorDescription = {
      message: e.message,
      retryable: e.retryable ?? e.is_retryable ?? false,
    };
    if (typeof e.code === "string") out.code = e.code;
    return out;
  }
  return { message: String(err), retryable: false };
}
