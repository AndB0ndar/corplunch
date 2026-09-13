const TOKEN_KEY = 'corplunch.access_token';

let memoryToken: string | null | undefined;

export function getToken(): string | null {
  if (memoryToken !== undefined) {
    return memoryToken;
  }
  memoryToken = localStorage.getItem(TOKEN_KEY);
  return memoryToken;
}

export function setToken(token: string | null): void {
  memoryToken = token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    return;
  }
  localStorage.removeItem(TOKEN_KEY);
}
