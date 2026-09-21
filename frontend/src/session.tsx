import { createContext, useContext } from 'react';
import type { AppApi, User } from './types';
export type Session = {
  api: AppApi;
  user: User;
  demo: boolean;
  logout: () => void;
};
export const SessionContext = createContext<Session | null>(null);
export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error('Session is missing');
  return session;
}
