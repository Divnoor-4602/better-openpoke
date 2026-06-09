import { cn } from '@general-poke/ui'

export const MaxWidthWrapper = ({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) => {
  return (
    <div className={cn('mx-auto w-full max-w-[min(1000px,100%)]', className)}>
      {children}
    </div>
  )
}
