import { useState } from 'react'
import { toast } from 'sonner'
import { useCreateTestCase } from '@/features/playground/api'
import { ApiError } from '@/shared/api/problem'
import { type CheckRequest, type Decision, type RuleInfo, VERDICTS, type Verdict } from '@/shared/api/types'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { NativeSelect } from '@/shared/ui/native-select'

interface Props {
  checkRequest: CheckRequest
  decision: Decision
  rules: Record<string, RuleInfo>
}

export function SaveTestCase({ checkRequest, decision, rules }: Props) {
  const matched = (decision.rule_results ?? []).filter((r) => r.matched)
  const [ruleId, setRuleId] = useState<string>(matched[0]?.rule_id ?? '')
  const [expected, setExpected] = useState<Verdict>(decision.verdict)
  const [name, setName] = useState('')
  const create = useCreateTestCase()

  const save = async () => {
    try {
      const tc = await create.mutateAsync({
        rule_id: ruleId || null,
        name: name || `${checkRequest.request.tool ?? checkRequest.request.kind} (${expected})`,
        check_request: checkRequest,
        expected_verdict: expected,
        origin: 'playground',
      })
      toast.success(`Saved test case “${tc.name}”${ruleId ? ` for ${rules[ruleId]?.name ?? ruleId}` : ' (policy-wide)'}`)
      setName('')
    } catch (err) {
      toast.error('Could not save test case', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed p-3" data-testid="save-test-case">
      <div className="text-xs font-medium">Save as test case</div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <NativeSelect aria-label="Test case rule" value={ruleId} onChange={(e) => setRuleId(e.target.value)}>
          {matched.map((r) => (
            <option key={r.rule_id} value={r.rule_id}>
              {rules[r.rule_id]?.name ?? r.rule_id}
            </option>
          ))}
          <option value="">Whole policy</option>
        </NativeSelect>
        expect
        <NativeSelect aria-label="Expected verdict" value={expected} onChange={(e) => setExpected(e.target.value as Verdict)}>
          {VERDICTS.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </NativeSelect>
        <Input aria-label="Test case name" className="h-8 w-56" placeholder="name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
        <Button size="sm" onClick={save} disabled={create.isPending}>
          Save
        </Button>
      </div>
    </div>
  )
}
