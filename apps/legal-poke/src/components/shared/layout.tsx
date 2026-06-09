import { cn } from '@general-poke/ui'

type LayoutProps = React.ComponentProps<'main'>

export const Layout = ({ className, ...props }: LayoutProps) => {
  return (
    <main className={cn('min-h-dvh bg-background', className)} {...props} />
  )
}

type LayoutContentProps = React.ComponentProps<'div'>

export const LayoutContent = ({ className, ...props }: LayoutContentProps) => {
  return (
    <div className={cn('mx-auto w-full max-w-5xl p-6', className)} {...props} />
  )
}
