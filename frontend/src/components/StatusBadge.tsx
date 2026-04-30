import clsx from 'clsx'

import { STATUS_COPY } from '../lib/statusCopy'
import type { MeetingStatus } from '../types'

type StatusBadgeProps = {
  status: MeetingStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const copy = STATUS_COPY[status]

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        copy.className,
      )}
    >
      {copy.showLiveDot ? <span className="h-1.5 w-1.5 rounded-full bg-red-400" /> : null}
      {copy.label}
    </span>
  )
}
