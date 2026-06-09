import { SignUp } from '@clerk/tanstack-react-start'
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/(auth)/sign-up/$')({
  component: SignUpPage,
})

function SignUpPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <SignUp
        forceRedirectUrl="/"
        path="/sign-up"
        routing="path"
        signInUrl="/sign-in"
      />
    </main>
  )
}
