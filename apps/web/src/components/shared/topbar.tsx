import { cn } from '@/lib/utils'

import { Separator } from '@general-poke/ui/components/separator'

type TopbarProps = React.ComponentProps<'div'>

export const Topbar = ({ className, ...props }: TopbarProps) => {
  return (
    <div
      className={cn(
        'absolute top-0 inset-x-0 z-20 flex items-center justify-between py-2.5 px-2 pointer-events-none *:pointer-events-auto',
        className,
      )}
      {...props}
    />
  )
}

type TopbarSectionProps = React.ComponentProps<'div'>

export const TopbarLeft = ({ className, ...props }: TopbarSectionProps) => {
  return <div className={cn('flex items-center', className)} {...props} />
}

export const TopbarRight = ({ className, ...props }: TopbarSectionProps) => {
  return <div className={cn('flex items-center', className)} {...props} />
}

type TopbarMenuProps = React.ComponentProps<'div'>

export const TopbarMenu = ({ className, ...props }: TopbarMenuProps) => {
  return (
    <div
      className={cn(
        'flex h-7.5 items-center px-1 border rounded-poke bg-white gap-1',
        className,
      )}
      {...props}
    />
  )
}

type TopbarMenuGroupProps = React.ComponentProps<'div'> & {
  separated?: boolean
}

export const TopbarMenuGroup = ({
  className,
  separated = true,
  ...props
}: TopbarMenuGroupProps) => {
  return (
    <>
      {separated && <Separator orientation="vertical" />}
      <div className={cn('flex items-center gap-0.5', className)} {...props} />
    </>
  )
}
