import { lazy, Suspense } from 'react'

import { LoginForm } from './form/login-form'
import { ShaderFallback } from './shader-fallback'

const ShaderEffect = lazy(() =>
  import('./shader-effect').then((m) => ({ default: m.ShaderEffect })),
)

export const LoginLayout = () => {
  return (
    <div className="h-svh w-screen flex">
      <div className="flex flex-1 flex-col gap-4 p-6 md:p-10">
        <div className="flex flex-1 items-center justify-center">
          <div className="max-w-sm flex flex-col items-center w-full gap-8">
            <div className="flex flex-col gap-4 items-center">
              <div className="font-heading font-bold text-4xl text-foreground tracking-tight">
                General Poke
              </div>
              <span className="font-normal text-muted-foreground text-13 text-center">
                General Poke is a 24/7 assistant that manages your life
              </span>
            </div>

            <LoginForm />
          </div>
        </div>
      </div>
      <div className="relative hidden w-1/2 lg:block bg-neutral-100">
        <Suspense fallback={<ShaderFallback />}>
          <ShaderEffect />
        </Suspense>
      </div>
    </div>
  )
}
