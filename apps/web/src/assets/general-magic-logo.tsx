import type { SVGProps } from 'react'

interface GeneralMagicLogoProps extends SVGProps<SVGSVGElement> {
  animating?: boolean
  defaultColor?: string
  quadrantColors?: QuadrantColors
}

interface QuadrantColors {
  bottomLeft?: string
  bottomRight?: string
  topLeft?: string
  topRight?: string
}

const CYCLE_DURATION = '1.2s'
const CYCLE_DELAYS = ['0s', '-0.9s', '-0.6s', '-0.3s'] // TL, TR, BR, BL — each 25% of 1.2s apart

export function GeneralMagicLogo({
  animating = false,
  defaultColor = '#B1B1B1',
  quadrantColors,
  ...props
}: GeneralMagicLogoProps) {
  const tl = quadrantColors?.topLeft ?? defaultColor
  const tr = quadrantColors?.topRight ?? defaultColor
  const bl = quadrantColors?.bottomLeft ?? defaultColor
  const br = quadrantColors?.bottomRight ?? defaultColor

  const groupStyle = (fill: string, delayIndex: number): React.CSSProperties =>
    animating
      ? {
          animation: `indicator-cycle ${CYCLE_DURATION} ease-in-out infinite`,
          animationDelay: CYCLE_DELAYS[delayIndex],
        }
      : { fill, transition: 'fill 300ms ease' }

  return (
    <svg
      fill="none"
      height="54"
      viewBox="0 0 54 54"
      width="54"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      {/* top-left */}
      <g fill={animating ? undefined : tl} style={groupStyle(tl, 0)}>
        <rect
          height="1.8"
          transform="rotate(180 12.8995 17.8995)"
          width="5"
          x="12.8995"
          y="17.8995"
        />
        <rect
          height="1.8"
          transform="rotate(90 17.7995 8.83339)"
          width="5"
          x="17.7995"
          y="8.83339"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(-135 4.94975 21.8995)"
          width="7"
          x="4.94975"
          y="21.8995"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(-135 16.9498 9.89949)"
          width="7"
          x="16.9498"
          y="9.89949"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(-135 16.9498 21.8995)"
          width="7"
          x="16.9498"
          y="21.8995"
        />
      </g>
      {/* top-right */}
      <g fill={animating ? undefined : tr} style={groupStyle(tr, 1)}>
        <rect
          height="1.8"
          transform="matrix(0 -1 1 0 23 48.799)"
          width="5"
          x="35.8995"
          y="12.8995"
        />
        <rect
          height="1.8"
          transform="rotate(-180 44.9656 17.7995)"
          width="5"
          x="44.9656"
          y="17.7995"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(-45 31.8995 4.94974)"
          width="7"
          x="31.8995"
          y="4.94974"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(-45 43.8995 16.9497)"
          width="7"
          x="43.8995"
          y="16.9497"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(-45 31.8995 16.9497)"
          width="7"
          x="31.8995"
          y="16.9497"
        />
      </g>
      {/* bottom-left */}
      <g fill={animating ? undefined : bl} style={groupStyle(bl, 3)}>
        <rect
          height="1.8"
          transform="rotate(90 17.8995 40.8995)"
          width="5"
          x="17.8995"
          y="40.8995"
        />
        <rect height="1.8" width="5" x="8.8334" y="35.9995" />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(135 21.8995 48.8492)"
          width="7"
          x="21.8995"
          y="48.8492"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(135 9.8995 36.8492)"
          width="7"
          x="9.8995"
          y="36.8492"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(135 21.8995 36.8492)"
          width="7"
          x="21.8995"
          y="36.8492"
        />
      </g>
      {/* bottom-right */}
      <g fill={animating ? undefined : br} style={groupStyle(br, 2)}>
        <rect height="1.8" width="5" x="40.8995" y="35.8995" />
        <rect
          height="1.8"
          transform="rotate(-90 35.9995 44.9656)"
          width="5"
          x="35.9995"
          y="44.9656"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(45 48.8492 31.8995)"
          width="7"
          x="48.8492"
          y="31.8995"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(45 36.8492 43.8995)"
          width="7"
          x="36.8492"
          y="43.8995"
        />
        <rect
          height="7"
          rx="2.1"
          transform="rotate(45 36.8492 31.8995)"
          width="7"
          x="36.8492"
          y="31.8995"
        />
      </g>
    </svg>
  )
}
