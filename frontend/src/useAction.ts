import {
  useMutation,
  useQueryClient,
  type MutationKey,
} from '@tanstack/react-query';
import { ApiError } from './api';
export function useAction<T>(
  fn: (value: T) => Promise<unknown>,
  mutationKey?: MutationKey,
) {
  const client = useQueryClient();
  return useMutation({
    mutationKey,
    mutationFn: fn,
    onSuccess: async () => {
      await client.invalidateQueries();
    },
    onError: async (error) => {
      if (error instanceof ApiError && [403, 409].includes(error.status))
        await client.invalidateQueries();
    },
  });
}
