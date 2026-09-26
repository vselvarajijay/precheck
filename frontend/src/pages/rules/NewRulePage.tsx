import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { ApiError, errorsByPath } from '@/api/problem'
import { useCreateRule } from '@/api/rules'
import { GATES, type Gate, type RuleBody } from '@/api/types'
import { RuleBodyEditor } from '@/components/rules/RuleBodyEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/ui-extra/native-select'
import { emptyBody } from '@/lib/ruleBody'

export function NewRulePage() {
  const navigate = useNavigate()
  const create = useCreateRule()
  const [name, setName] = useState('')
  const [gate, setGate] = useState<Gate>('tool_call')
  const [sourceText, setSourceText] = useState('')
  const [explanation, setExplanation] = useState('')
  const [body, setBody] = useState<RuleBody>(emptyBody)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const rule = await create.mutateAsync({
        name,
        gate,
        body,
        source_text: sourceText || null,
        explanation: explanation || null,
      })
      toast.success(`Created ${rule.name} (v1, draft)`)
      navigate(`/rules/${rule.id}`)
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(errorsByPath(err.fieldErrors, 'body.'))
        toast.error(err.problem?.title ?? 'Could not create rule', { description: err.message })
      } else toast.error('Could not create rule')
    }
  }

  return (
    <form className="max-w-4xl space-y-4" onSubmit={submit} aria-label="New rule">
      <h1 className="text-xl font-semibold">New rule</h1>
      <p className="text-sm text-muted-foreground">
        Write the rule by hand. (Translating from a plain-language business case comes later.)
      </p>
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="text-sm">
          Name
          <Input aria-label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
          {errors.name && <span className="text-xs text-destructive">{errors.name.join('; ')}</span>}
        </label>
        <label className="text-sm">
          Gate
          <NativeSelect aria-label="Gate" className="block w-40" value={gate} onChange={(e) => setGate(e.target.value as Gate)}>
            {GATES.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </NativeSelect>
        </label>
      </div>
      <label className="block text-sm">
        Source text (the business-case sentence this rule comes from)
        <Textarea aria-label="Source text" rows={2} value={sourceText} onChange={(e) => setSourceText(e.target.value)} />
      </label>
      <label className="block text-sm">
        Explanation (plain-language restatement)
        <Textarea aria-label="Explanation" rows={2} value={explanation} onChange={(e) => setExplanation(e.target.value)} />
      </label>
      <RuleBodyEditor value={body} onChange={setBody} errors={errors} />
      <div className="flex gap-2">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? 'Saving…' : 'Create draft'}
        </Button>
        <Button type="button" variant="ghost" onClick={() => navigate('/rules')}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
