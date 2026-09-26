import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/health')
      if (error || !data) throw new Error('API unreachable')
      return data
    },
    refetchInterval: 15_000,
    retry: 1,
  })
}
