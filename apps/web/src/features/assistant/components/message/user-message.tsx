import { formatClock } from '../../lib/format-time'

type UserMessageProps = {
  createdAt: number
  text: string
}

export const UserMessage = ({ createdAt, text }: UserMessageProps) => (
  <div className="flex flex-col items-end gap-1">
    <div className="ml-12 rounded-2xl rounded-tr-[4px] bg-muted px-5 py-3 text-sm @[420px]/thread:ml-0 @[420px]/thread:max-w-[calc(100%-3rem)]">
      <p className="whitespace-pre-wrap leading-relaxed">{text}</p>
    </div>
    <time className="text-xs tabular-nums text-muted-foreground/70 pr-2 mt-1">
      {formatClock(createdAt)}
    </time>
  </div>
)
