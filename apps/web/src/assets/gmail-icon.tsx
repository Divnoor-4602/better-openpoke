import type { SVGProps } from 'react'

const GmailIcon = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg
      fill="none"
      viewBox="0 0 75 56"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <path
        d="M5.1 56H17V27.2L0 14.4v36.5A5.1 5.1 0 0 0 5.1 56Z"
        fill="#4285F4"
      />
      <path
        d="M57.7 56h11.9a5.1 5.1 0 0 0 5.1-5.1V14.4l-17 12.8V56Z"
        fill="#34A853"
      />
      <path
        d="M57.7 5.1v22.1l17-12.7V7.6c0-6.3-7.2-9.9-12.2-6.1L57.7 5.1Z"
        fill="#FBBC04"
      />
      <path
        d="M17 27.2V5.1l20.3 15.3L57.7 5.1v22.1L37.3 42.4 17 27.2Z"
        fill="#EA4335"
      />
      <path
        d="M0 7.6v6.8L17 27.1V5.1l-4.8-3.6C7.2-2.2 0 1.4 0 7.6Z"
        fill="#C5221F"
      />
    </svg>
  )
}

export default GmailIcon
