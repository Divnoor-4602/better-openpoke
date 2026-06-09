import { useState } from 'react'

type Props = {
  cancelLabel?: string
  confirmLabel?: string
  isPending?: boolean
  onCancel: () => void
  onConfirm: () => void
  open: boolean
  text: string
  title: string
}

export const ConsentModal = ({
  cancelLabel = 'Cancel',
  confirmLabel = 'I confirm',
  isPending,
  onCancel,
  onConfirm,
  open,
  text,
  title,
}: Props) => {
  const [acknowledged, setAcknowledged] = useState(false)

  if (!open) return null

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="flex w-full max-w-md flex-col gap-4 rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-gray-700">{text}</p>
        <label className="flex items-start gap-2 text-sm">
          <input
            checked={acknowledged}
            className="mt-0.5"
            disabled={isPending}
            onChange={(e) => setAcknowledged(e.target.checked)}
            type="checkbox"
          />
          <span>I acknowledge the statement above.</span>
        </label>
        <div className="flex justify-end gap-2">
          <button
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
            disabled={isPending}
            onClick={() => {
              setAcknowledged(false)
              onCancel()
            }}
            type="button"
          >
            {cancelLabel}
          </button>
          <button
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={!acknowledged || isPending}
            onClick={() => {
              setAcknowledged(false)
              onConfirm()
            }}
            type="button"
          >
            {isPending ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
