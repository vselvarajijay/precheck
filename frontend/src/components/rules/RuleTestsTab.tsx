import { Link } from 'react-router'
import { useRuleTestCases } from '@/api/playground'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { VerdictBadge } from './badges'

export function RuleTestsTab({ ruleId }: { ruleId: string }) {
  const { data, isPending } = useRuleTestCases(ruleId)
  return (
    <div className="space-y-3" data-testid="rule-tests">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {data ? `${data.length} test case${data.length === 1 ? '' : 's'}` : 'Loading…'} · runs and calibration arrive with the Tests slice.
        </p>
        <Button asChild variant="outline" size="sm">
          <Link to={`/playground?rule=${encodeURIComponent(ruleId)}`}>Try in playground</Link>
        </Button>
      </div>
      {!isPending && data && data.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case</TableHead>
              <TableHead>Expected</TableHead>
              <TableHead>Origin</TableHead>
              <TableHead>Request</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((tc) => (
              <TableRow key={tc.id}>
                <TableCell>{tc.name}</TableCell>
                <TableCell>
                  <VerdictBadge verdict={tc.expected_verdict} />
                </TableCell>
                <TableCell className="text-xs">{tc.origin}</TableCell>
                <TableCell className="max-w-xs truncate font-mono text-xs">
                  {tc.check_request.request.tool ?? tc.check_request.request.kind}{' '}
                  {JSON.stringify(tc.check_request.request.args ?? {})}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
