import { CopyButton } from '@/components/ui/copy-button'

type DraftEmailCopyButtonProps = {
  body: string
  subject: string
}

export const DraftEmailCopyButton = ({
  body,
  subject,
}: DraftEmailCopyButtonProps) => {
  return (
    <CopyButton
      ariaLabelCopied="Copied email draft"
      ariaLabelIdle="Copy email draft"
      text={getDraftCopyText(subject, body)}
    />
  )
}

const getDraftCopyText = (subject: string, body: string) => {
  return `Subject: ${subject}\n\n${body}`
}
