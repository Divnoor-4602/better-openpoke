import { cn } from '@general-poke/ui'

export const MaxWidthWrapper = ({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) => {
  return (
    <div
      className={cn(
        '@container/chat-container mx-auto w-full max-w-[min(700px,100%)]',
        className,
      )}
    >
      {children}
    </div>
  )
}
