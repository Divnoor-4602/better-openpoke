import type { UseInViewOptions } from 'motion/react'

import { motion, useInView } from 'motion/react'
import React, { useRef } from 'react'

import { cn } from '@general-poke/ui/lib/utils'

interface ShimmeringTextProps {
  className?: string
  color?: string
  delay?: number
  duration?: number
  inViewMargin?: UseInViewOptions['margin']
  once?: boolean
  repeat?: boolean
  repeatDelay?: number
  repeatType?: 'loop' | 'mirror' | 'reverse'
  shimmerColor?: string
  spread?: number
  startOnView?: boolean
  text: string
}

export function ShimmeringText({
  className,
  color,
  delay = 0,
  duration = 2,
  inViewMargin,
  once = false,
  repeat = true,
  repeatDelay = 0.5,
  repeatType = 'loop',
  shimmerColor,
  spread = 2,
  startOnView = true,
  text,
}: ShimmeringTextProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const isInView = useInView(ref, { margin: inViewMargin, once })

  const dynamicSpread = text.length * spread

  const shouldAnimate = !startOnView || isInView

  return (
    <motion.span
      animate={
        shouldAnimate ? { backgroundPosition: '0% center', opacity: 1 } : {}
      }
      className={cn(
        'relative inline-block bg-size-[250%_100%,auto] bg-clip-text text-transparent',
        '[--base-color:var(--muted-foreground)] [--shimmer-color:var(--foreground)]',
        '[background-repeat:no-repeat,padding-box]',
        '[--shimmer-bg:linear-gradient(90deg,transparent_calc(50%-var(--spread)),var(--shimmer-color),transparent_calc(50%+var(--spread)))]',
        className,
      )}
      inherit={false}
      initial={{ backgroundPosition: '100% center', opacity: 0 }}
      ref={ref}
      style={
        {
          '--spread': `${dynamicSpread}px`,
          ...(color && { '--base-color': color }),
          ...(shimmerColor && { '--shimmer-color': shimmerColor }),
          backgroundImage: `var(--shimmer-bg), linear-gradient(var(--base-color), var(--base-color))`,
        } as React.CSSProperties
      }
      transition={{
        backgroundPosition: {
          delay,
          duration,
          ease: 'linear',
          repeat: repeat ? Infinity : 0,
          repeatDelay,
          repeatType,
        },
        opacity: { delay, duration: 0.3 },
      }}
    >
      {text}
    </motion.span>
  )
}
