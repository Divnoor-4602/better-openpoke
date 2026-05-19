import { cn } from '@/lib/utils'

import { MaxWidthWrapper } from './max-width-wrapper'

type LayoutProps = React.ComponentProps<'div'>

export const Layout = ({ children, className, ...props }: LayoutProps) => {
  return (
    <div className={cn('bg-background h-dvh relative', className)} {...props}>
      {children}
    </div>
  )
}

type LayoutContentProps = React.ComponentProps<'div'> & {
  unwrapped?: boolean
}

export const LayoutContent = ({
  children,
  className,
  unwrapped,
  ...props
}: LayoutContentProps) => {
  return (
    <div
      className={cn(
        'absolute inset-0 scrollbar-thin [scrollbar-color:#e5e5e5_transparent]',
        unwrapped ? 'overflow-hidden' : 'overflow-y-auto',
        className,
      )}
      {...props}
    >
      {unwrapped ? (
        children
      ) : (
        <MaxWidthWrapper className="flex flex-col min-h-full pt-14">
          {children}
        </MaxWidthWrapper>
      )}
    </div>
  )
}
