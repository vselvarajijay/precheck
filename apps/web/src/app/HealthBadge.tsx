import { useHealth } from '@/shared/api/hooks'
import { Badge } from '@/shared/ui/badge'

export function HealthBadge() {
  const { data, isPending, isError } = useHealth()
  if (isPending) return <Badge variant="outline">Checking API…</Badge>
  if (isError || !data) return <Badge variant="destructive">API down</Badge>
  return (
    <Badge variant={data.jev_configured ? 'secondary' : 'outline'} data-testid="health-badge">
      {`API ok · ${data.jev_configured ? 'Jev configured' : 'Jev not configured'}`}
    </Badge>
  )
}
