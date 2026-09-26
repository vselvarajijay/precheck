import { PlusIcon, XIcon } from 'lucide-react'
import { useId } from 'react'
import type { Predicate } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui-extra/native-select'
import { CHECK_PATHS, defaultPredicate, PREDICATE_OPS, type PredicateOp } from '@/lib/ruleBody'
import { FieldErrors } from './FieldErrors'

type Scalar = string | number | boolean | null
type ValueType = 'string' | 'number' | 'boolean' | 'null'

function typeOf(v: Scalar | undefined): ValueType {
  if (v === null) return 'null'
  if (typeof v === 'number') return 'number'
  if (typeof v === 'boolean') return 'boolean'
  return 'string'
}

function coerce(raw: string, t: ValueType): Scalar {
  if (t === 'number') return raw.trim() === '' ? 0 : Number(raw)
  if (t === 'boolean') return raw === 'true'
  if (t === 'null') return null
  return raw
}

const splitList = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)

interface Props {
  value: Predicate
  onChange: (p: Predicate) => void
  onRemove?: () => void
  /** RuleBody path for error display, e.g. `applies_when`. */
  errorPath: string
  depth?: number
  label?: string
}

export function PredicateBuilder({ value, onChange, onRemove, errorPath, depth = 0, label }: Props) {
  const listId = useId()
  const p = value
  const opLabel = label ?? 'Condition'

  const changeOp = (op: PredicateOp) => {
    const path = 'path' in p ? p.path : undefined
    onChange(defaultPredicate(op, path))
  }

  return (
    <div
      className={depth > 0 ? 'rounded-md border-l-2 border-muted pl-3' : ''}
      data-testid={`predicate-${errorPath}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {'path' in p && (
          <>
            <Input
              aria-label={`${opLabel} field`}
              className="h-8 w-52 font-mono text-xs"
              list={listId}
              value={p.path}
              onChange={(e) => onChange({ ...p, path: e.target.value } as Predicate)}
            />
            <datalist id={listId}>
              {CHECK_PATHS.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </>
        )}
        <NativeSelect aria-label={`${opLabel} operator`} value={p.op} onChange={(e) => changeOp(e.target.value as PredicateOp)}>
          {PREDICATE_OPS.map((o) => (
            <option key={o.op} value={o.op}>
              {o.label}
            </option>
          ))}
        </NativeSelect>
        <LeafValue p={p} onChange={onChange} label={opLabel} />
        {onRemove && (
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove condition" onClick={onRemove}>
            <XIcon />
          </Button>
        )}
      </div>

      {(p.op === 'all' || p.op === 'any') && (
        <div className="mt-2 space-y-2">
          {p.predicates.map((child, i) => (
            <PredicateBuilder
              key={i}
              value={child}
              depth={depth + 1}
              errorPath={`${errorPath}.predicates.${i}`}
              onChange={(c) => onChange({ ...p, predicates: p.predicates.map((x, j) => (j === i ? c : x)) })}
              onRemove={
                p.predicates.length > 1
                  ? () => onChange({ ...p, predicates: p.predicates.filter((_, j) => j !== i) })
                  : undefined
              }
            />
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onChange({ ...p, predicates: [...p.predicates, defaultPredicate('eq')] })}
          >
            <PlusIcon /> Add condition
          </Button>
        </div>
      )}
      {p.op === 'not' && (
        <div className="mt-2">
          <PredicateBuilder
            value={p.predicate}
            depth={depth + 1}
            errorPath={`${errorPath}.predicate`}
            onChange={(c) => onChange({ ...p, predicate: c })}
          />
        </div>
      )}
      <FieldErrors path={errorPath} exact />
    </div>
  )
}

function LeafValue({ p, onChange, label }: { p: Predicate; onChange: (p: Predicate) => void; label: string }) {
  switch (p.op) {
    case 'eq':
    case 'ne': {
      const t = typeOf(p.value)
      return (
        <>
          <NativeSelect
            aria-label={`${label} value type`}
            value={t}
            onChange={(e) => onChange({ ...p, value: coerce(String(p.value ?? ''), e.target.value as ValueType) })}
          >
            <option value="string">text</option>
            <option value="number">number</option>
            <option value="boolean">true/false</option>
            <option value="null">null</option>
          </NativeSelect>
          {t === 'boolean' ? (
            <NativeSelect
              aria-label={`${label} value`}
              value={String(p.value)}
              onChange={(e) => onChange({ ...p, value: e.target.value === 'true' })}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </NativeSelect>
          ) : t !== 'null' ? (
            <Input
              aria-label={`${label} value`}
              className="h-8 w-44"
              type={t === 'number' ? 'number' : 'text'}
              value={String(p.value ?? '')}
              onChange={(e) => onChange({ ...p, value: coerce(e.target.value, t) })}
            />
          ) : null}
        </>
      )
    }
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
      return (
        <Input
          aria-label={`${label} value`}
          className="h-8 w-32"
          type="number"
          value={String(p.value ?? 0)}
          onChange={(e) => onChange({ ...p, value: Number(e.target.value) })}
        />
      )
    case 'in':
    case 'not_in':
      return (
        <Input
          aria-label={`${label} values (comma separated)`}
          className="h-8 w-64"
          placeholder="a, b, c"
          value={p.values.map((v) => String(v)).join(', ')}
          onChange={(e) => onChange({ ...p, values: splitList(e.target.value) })}
        />
      )
    case 'regex':
      return (
        <Input
          aria-label={`${label} pattern`}
          className="h-8 w-56 font-mono text-xs"
          value={p.pattern}
          onChange={(e) => onChange({ ...p, pattern: e.target.value })}
        />
      )
    case 'min_len':
      return (
        <Input
          aria-label={`${label} minimum length`}
          className="h-8 w-24"
          type="number"
          min={0}
          value={p.value}
          onChange={(e) => onChange({ ...p, value: Math.max(0, Number(e.target.value)) })}
        />
      )
    case 'domain_in':
    case 'domain_not_in':
      return (
        <Input
          aria-label={`${label} domains (comma separated)`}
          className="h-8 w-64"
          value={p.domains.join(', ')}
          onChange={(e) => onChange({ ...p, domains: splitList(e.target.value) })}
        />
      )
    default:
      return null
  }
}
