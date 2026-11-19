export async function readError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail ?? `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}
